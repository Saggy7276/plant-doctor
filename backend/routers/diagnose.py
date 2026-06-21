import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from langgraph.types import Command
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
import models
import schemas

# agent/ is at the project root, two levels above this file
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent.graph import plant_graph, PlantAgentState  # noqa: E402

router = APIRouter()
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")


# ── helpers ───────────────────────────────────────────────────────────────────

def _save_upload(file: UploadFile, user_id: int, plant_id: int) -> str:
    ext  = Path(file.filename or "upload").suffix.lower() or ".jpg"
    dest = Path(UPLOAD_DIR) / str(user_id) / str(plant_id)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{uuid.uuid4().hex}{ext}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return str(path)


def _thread_id(user_id: int, plant_id: int) -> str:
    return f"u{user_id}-p{plant_id}-{uuid.uuid4().hex[:8]}"


def _guard_plant(plant_id: int, user_id: int, db: Session) -> models.Plant:
    plant = db.query(models.Plant).filter(
        models.Plant.id == plant_id,
        models.Plant.owner_id == user_id,
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return plant


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{plant_id}", response_model=schemas.DiagnoseStartOut)
def start_diagnosis(
    plant_id: int,
    file: UploadFile = File(...),
    species: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Upload a plant photo and start the diagnosis agent.
    Runs identify → diagnose → ask_clarifying_questions, then pauses.
    Returns the thread_id (needed for /resume) and the generated questions.
    """
    _guard_plant(plant_id, current_user.id, db)
    image_path = _save_upload(file, current_user.id, plant_id)
    thread_id  = _thread_id(current_user.id, plant_id)
    config     = {"configurable": {"thread_id": thread_id}}

    initial: PlantAgentState = {
        "plant_id":             str(plant_id),
        "species":              species or "",
        "image_path":           image_path,
        "diagnosis":            {},
        "clarifying_questions": [],
        "user_answers":         "",
        "care_plan":            "",
        "phase":                "identify",
        "followup_image_path":  "",
        "progress":             "",
        "changes":              [],
    }

    try:
        result = plant_graph.invoke(initial, config=config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {exc}") from exc

    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        raise HTTPException(
            status_code=500,
            detail="Graph completed without pausing — interrupt() may be missing.",
        )

    questions: list[str] = interrupts[0].value.get("questions", [])
    diagnosis: dict      = result.get("diagnosis", {})

    return schemas.DiagnoseStartOut(
        thread_id=thread_id,
        questions=questions,
        diagnosis=diagnosis,
    )


@router.post("/{plant_id}/resume", response_model=schemas.DiagnoseResumeOut)
def resume_diagnosis(
    plant_id: int,
    body: schemas.DiagnoseResumeIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Resume the paused agent with the user's answers.
    Runs prescribe_care_plan, then saves Diagnosis + CarePlan to the DB.
    Returns the care plan and the saved record IDs.
    """
    _guard_plant(plant_id, current_user.id, db)
    config = {"configurable": {"thread_id": body.thread_id}}

    try:
        final = plant_graph.invoke(Command(resume=body.answers), config=config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Care plan generation failed: {exc}") from exc

    care_plan_text = final.get("care_plan", "")
    diagnosis_dict = final.get("diagnosis", {})
    image_path     = final.get("image_path", "")

    if not care_plan_text:
        raise HTTPException(status_code=500, detail="Agent returned an empty care plan.")

    # ── persist Diagnosis ─────────────────────────────────────────────────────
    diagnosis_row = models.Diagnosis(
        image_path=image_path,
        result=diagnosis_dict.get("issue_category"),
        confidence=diagnosis_dict.get("confidence"),
        plant_id=plant_id,
        user_id=current_user.id,
        thread_id=body.thread_id,
    )
    db.add(diagnosis_row)
    db.flush()  # get diagnosis_row.id before creating CarePlan

    # ── persist CarePlan ──────────────────────────────────────────────────────
    issue     = diagnosis_dict.get("issue_category", "issue")
    species   = final.get("species", "plant")
    care_row  = models.CarePlan(
        title=f"Care plan: {species} — {issue}",
        content=care_plan_text,
        plant_id=plant_id,
        user_id=current_user.id,
        diagnosis_id=diagnosis_row.id,
    )
    db.add(care_row)
    db.commit()
    db.refresh(diagnosis_row)
    db.refresh(care_row)

    return schemas.DiagnoseResumeOut(
        care_plan=care_plan_text,
        diagnosis_id=diagnosis_row.id,
        care_plan_id=care_row.id,
    )


@router.post("/{plant_id}/checkin", response_model=schemas.CheckinOut)
def checkin(
    plant_id: int,
    file: UploadFile = File(..., description="New photo of the plant taken ~7 days after the original diagnosis"),
    thread_id: str = Form(..., description="thread_id returned by the original /diagnose/{plant_id} call"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    7-day follow-up: upload a new photo, compare with the original, get an updated care plan.

    Requires:
    - file  — the NEW photo (real image of the plant, taken now)
    - thread_id — the thread_id you received from the original diagnosis call
    """
    _guard_plant(plant_id, current_user.id, db)

    # ── load original state from checkpoint ───────────────────────────────────
    orig_config   = {"configurable": {"thread_id": thread_id}}
    orig_snapshot = plant_graph.get_state(orig_config)
    if not orig_snapshot or not orig_snapshot.values:
        raise HTTPException(
            status_code=404,
            detail=f"No checkpoint found for thread_id={thread_id!r}. "
                   "Make sure you complete a diagnosis first.",
        )
    orig = orig_snapshot.values

    if not orig.get("image_path"):
        raise HTTPException(
            status_code=422,
            detail="Original diagnosis has no image_path in its checkpoint.",
        )
    if not orig.get("care_plan"):
        raise HTTPException(
            status_code=422,
            detail="Original diagnosis has no care plan yet. Complete the /resume step first.",
        )

    # ── save the new photo ────────────────────────────────────────────────────
    new_image_path = _save_upload(file, current_user.id, plant_id)

    # ── run followup on a derived thread (keeps the original intact) ──────────
    checkin_thread = f"{thread_id}-ck"
    checkin_config = {"configurable": {"thread_id": checkin_thread}}

    checkin_state: PlantAgentState = {
        **orig,                                  # carry over species, diagnosis, care_plan …
        "followup_image_path": new_image_path,
        "progress":            "",
        "changes":             [],
        "phase":               "checkin",        # routes to followup_node
    }

    try:
        final = plant_graph.invoke(checkin_state, config=checkin_config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Check-in agent failed: {exc}") from exc

    progress     = final.get("progress", "unknown")
    changes      = final.get("changes", [])
    updated_plan = final.get("care_plan", "")

    if not updated_plan:
        raise HTTPException(status_code=500, detail="Agent returned an empty updated care plan.")

    orig_image_path = orig.get("image_path", "")

    # ── persist: new Diagnosis row for the checkin photo ─────────────────────
    diagnosis_row = models.Diagnosis(
        image_path=new_image_path,
        result=orig.get("diagnosis", {}).get("issue_category"),
        confidence=orig.get("diagnosis", {}).get("confidence"),
        plant_id=plant_id,
        user_id=current_user.id,
        thread_id=thread_id,
    )
    db.add(diagnosis_row)
    db.flush()

    # ── persist: updated CarePlan ─────────────────────────────────────────────
    species  = orig.get("species", "plant")
    care_row = models.CarePlan(
        title=f"7-day update: {species} — {progress}",
        content=updated_plan,
        plant_id=plant_id,
        user_id=current_user.id,
        diagnosis_id=diagnosis_row.id,
    )
    db.add(care_row)
    db.commit()
    db.refresh(diagnosis_row)
    db.refresh(care_row)

    return schemas.CheckinOut(
        progress=progress,
        changes=changes,
        updated_care_plan=updated_plan,
        diagnosis_id=diagnosis_row.id,
        care_plan_id=care_row.id,
        original_image_path=orig_image_path,
        new_image_path=new_image_path,
    )


@router.get("/{plant_id}/latest-care-plan", response_model=schemas.CarePlanOut)
def latest_care_plan(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return the most recent care plan persisted for a plant."""
    _guard_plant(plant_id, current_user.id, db)
    row = (
        db.query(models.CarePlan)
        .filter(
            models.CarePlan.plant_id == plant_id,
            models.CarePlan.user_id  == current_user.id,
        )
        .order_by(models.CarePlan.created_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No care plan found for this plant.")
    return row


@router.get("/{plant_id}/latest-thread", response_model=schemas.LatestThreadOut)
def latest_thread(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return the thread_id + image_path of the most recent completed diagnosis for a plant."""
    _guard_plant(plant_id, current_user.id, db)
    row = (
        db.query(models.Diagnosis)
        .filter(
            models.Diagnosis.plant_id == plant_id,
            models.Diagnosis.user_id  == current_user.id,
            models.Diagnosis.thread_id.isnot(None),
        )
        .order_by(models.Diagnosis.created_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No completed diagnosis found for this plant. "
                   "Run a diagnosis first before doing a check-in.",
        )
    return schemas.LatestThreadOut(thread_id=row.thread_id, image_path=row.image_path)


@router.get("/history", response_model=List[schemas.DiagnosisOut])
def diagnosis_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Diagnosis)
        .filter(models.Diagnosis.user_id == current_user.id)
        .order_by(models.Diagnosis.created_at.desc())
        .all()
    )
