"""
agent/graph.py — LangGraph plant-doctor agent.

Normal flow — high confidence, unambiguous visual category:
    START → identify_species → diagnose → prescribe_care_plan → END

Normal flow — low confidence OR ambiguous category (water/light/uncertain):
    START → identify_species → diagnose → ask_clarifying_questions
          -(interrupt)→ prescribe_care_plan → END

Follow-up (checkin) flow:
    START → followup_node → END
    (triggered when phase == "checkin")

Routing rule after diagnose:
    issue_category in {overwatering, underwatering, light, uncertain}
        OR confidence < 0.7  →  ask_clarifying_questions
    otherwise               →  prescribe_care_plan directly
"""

import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import TypedDict

from openai import OpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

# Ensure both agent/ and backend/ are importable regardless of cwd
_AGENT_DIR   = str(Path(__file__).parent)
_BACKEND_DIR = str(Path(__file__).parent.parent / "backend")
for _p in (_AGENT_DIR, _BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from checkpointer import checkpointer                   # noqa: E402
from vision_service import identify as vision_identify, diagnose as vision_diagnose  # noqa: E402
from rag_service import retrieve as rag_retrieve        # noqa: E402

_VISION_MODEL = "gpt-4o"
_TEXT_MODEL   = "gpt-4o-mini"

# Categories where a single image cannot reliably distinguish the cause.
# These always go through Q&A regardless of confidence score.
_ALWAYS_CLARIFY      = {"overwatering", "underwatering", "light", "uncertain"}
_CONFIDENCE_THRESHOLD = 0.7


# ── state ─────────────────────────────────────────────────────────────────────

class PlantAgentState(TypedDict):
    plant_id:             str
    species:              str
    image_path:           str
    diagnosis:            dict
    clarifying_questions: list[str]
    user_answers:         str
    care_plan:            str
    phase:                str        # identify / diagnose / clarify / prescribe / checkin / done
    user_context:         str        # optional text pasted by user (Reddit / Google) at upload time
    # follow-up fields (populated only during checkin flow)
    followup_image_path:  str
    days_elapsed:         int        # calendar days between original diagnosis and checkin photo
    progress:             str        # improving / stable / worsening / no_visible_change
    changes:              list[str]


# ── shared helpers ────────────────────────────────────────────────────────────

def _openai_client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _openai_text(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    resp = _openai_client().chat.completions.create(
        model=_TEXT_MODEL, messages=msgs, temperature=0.4, max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def _encode_image(path: str) -> tuple[str, str]:
    ext  = Path(path).suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode(), mime


def _parse_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON; fall back to regex scan."""
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", clean, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"No JSON in model output: {raw!r}")


# ── nodes: normal flow ────────────────────────────────────────────────────────

def identify_species_node(state: PlantAgentState) -> dict:
    if state.get("species", "").strip():
        print(f"[identify] species known: {state['species']} — skip")
        return {"phase": "diagnose"}
    print(f"[identify] running species ID on: {state['image_path']}")
    result = vision_identify(state["image_path"])
    print(f"[identify] detected: {result['species']} (conf={result['confidence']})")
    return {"species": result["species"], "phase": "diagnose"}


def diagnose_node(state: PlantAgentState) -> dict:
    species = state.get("species") or None
    if species and species.lower() == "unknown":
        species = None
    print(f"[diagnose] species={species}")
    result = vision_diagnose(state["image_path"], known_species=species)
    print(f"[diagnose] {result['issue_category']} (conf={result['confidence']})")
    return {"diagnosis": dict(result), "phase": "clarify"}


def ask_clarifying_questions_node(state: PlantAgentState) -> dict:
    diagnosis = state["diagnosis"]
    species   = state.get("species", "Unknown")
    category  = diagnosis.get("issue_category", "uncertain")
    symptoms  = ", ".join(diagnosis.get("symptoms", []))
    evidence  = diagnosis.get("evidence", "")

    if category in _ALWAYS_CLARIFY:
        # Photo cannot distinguish water vs light vs nutrient vs uncertain.
        # Ask about care habits and environment — facts only the owner knows.
        system = (
            "You are a plant care assistant. A single photo cannot reliably distinguish "
            "between overwatering, underwatering, and light stress — these require "
            "owner-reported facts. Generate exactly 3 short, specific questions covering: "
            "(1) watering frequency and method, "
            "(2) light conditions (direction, hours of direct sun), "
            "(3) recent environmental changes (moved, repotted, temperature shifts). "
            "Return only a numbered list, nothing else."
        )
        prompt = (
            f"Plant: {species}\n"
            f"Suspected issue: {category} (photo evidence inconclusive)\n"
            f"Visible symptoms: {symptoms}\n\n"
            f"Ask 3 questions to determine the true cause from owner-reported facts."
        )
    else:
        # Clear visual category but confidence is below threshold.
        # Ask questions to confirm or rule out the suspected issue.
        system = (
            "You are a plant care assistant. A visual diagnosis was made with moderate "
            "confidence. Generate exactly 2-3 short, specific questions to confirm or "
            "rule out the suspected issue and improve the care plan. "
            "Return only a numbered list, nothing else."
        )
        prompt = (
            f"Plant: {species}\n"
            f"Suspected issue: {category} (confidence: {diagnosis.get('confidence')})\n"
            f"Visible symptoms: {symptoms}\n"
            f"Model evidence: {evidence}\n\n"
            f"What 2-3 questions would help confirm the diagnosis and refine the care plan?"
        )

    questions_raw = _openai_text(system=system, prompt=prompt, max_tokens=256)
    questions = [
        line.lstrip("0123456789.-) ").strip()
        for line in questions_raw.splitlines()
        if line.strip()
    ]
    print(f"[clarify] category={category}, routed to Q&A, questions: {questions}")

    user_answers = interrupt({
        "questions": questions,
        "prompt": "Please answer the questions above, then resume.",
    })
    print(f"[clarify] answered: {user_answers!r}")
    return {
        "clarifying_questions": questions,
        "user_answers": str(user_answers),
        "phase": "prescribe",
    }


def prescribe_care_plan_node(state: PlantAgentState) -> dict:
    diagnosis = state["diagnosis"]
    species   = state.get("species", "Unknown")
    answers   = state.get("user_answers", "").strip()

    if answers:
        answers_section = f"Owner's answers to clarifying questions:\n{answers}"
    else:
        answers_section = (
            "No clarifying questions were asked (high-confidence visual diagnosis). "
            "Base the care plan entirely on the observed symptoms and evidence."
        )

    # ── user-provided context (pasted at upload time) ─────────────────────────
    user_context = (state.get("user_context") or "").strip()
    if user_context:
        user_context_section = (
            f"Additional context provided by the plant owner "
            f"(from Reddit, Google, or their own notes — treat as supporting "
            f"information, not as a diagnosis override):\n{user_context}"
        )
    else:
        user_context_section = ""

    # ── RAG: retrieve relevant plant-care knowledge ───────────────────────────
    rag_query   = f"{species} {diagnosis.get('issue_category')} {' '.join(diagnosis.get('symptoms', []))}"
    rag_chunks  = rag_retrieve(rag_query, n_results=4)
    if rag_chunks:
        rag_lines = "\n\n".join(
            f"[{c['source']}] {c['text']}" for c in rag_chunks
        )
        rag_section = (
            f"Reference material from your knowledge base "
            f"(cite sources in the care plan where relevant):\n{rag_lines}"
        )
    else:
        rag_section = ""

    care_plan = _openai_text(
        system=(
            "You are an expert plant pathologist and horticulturist. "
            "Write a clear, actionable care plan in plain English. "
            "Use numbered steps. Be specific about quantities and timing. "
            "Where you draw on the reference material provided, cite the source "
            "in parentheses at the end of that step, e.g. (Source: UC IPM)."
        ),
        prompt=(
            f"Plant species: {species}\n"
            f"Diagnosed issue: {diagnosis.get('issue_category')}\n"
            f"Observed symptoms: {', '.join(diagnosis.get('symptoms', []))}\n"
            f"Visual evidence: {diagnosis.get('evidence', '')}\n"
            f"Confidence: {diagnosis.get('confidence')}\n\n"
            f"{answers_section}\n\n"
            f"{user_context_section}\n\n"
            f"{rag_section}\n\n"
            f"Write a complete care plan to treat the issue and prevent recurrence."
        ),
        max_tokens=1024,
    )
    print(f"[prescribe] care plan written ({len(care_plan)} chars), rag_chunks={len(rag_chunks)}")
    return {"care_plan": care_plan, "phase": "done"}


# ── node: follow-up / checkin ─────────────────────────────────────────────────

def followup_node(state: PlantAgentState) -> dict:
    """
    Compare original photo with a new photo taken ~7 days later.
    Returns progress assessment + updated care plan.
    """
    orig_path = state["image_path"]
    new_path  = state["followup_image_path"]
    species   = state.get("species", "Unknown")
    diagnosis = state.get("diagnosis", {})
    old_plan  = state.get("care_plan", "")

    days_elapsed = state.get("days_elapsed") or 7
    print(f"[followup] comparing {orig_path} vs {new_path} ({days_elapsed}d elapsed)")

    b64_orig, mime_orig = _encode_image(orig_path)
    b64_new,  mime_new  = _encode_image(new_path)

    prompt = (
        "You are a plant pathologist conducting a follow-up comparison.\n\n"
        f"Original diagnosis: {diagnosis.get('issue_category', 'unknown')}\n"
        f"Original symptoms: {', '.join(diagnosis.get('symptoms', []))}\n"
        f"Previous care plan:\n{old_plan}\n\n"
        f"Days since original photo: {days_elapsed} "
        "(context only — elapsed time is NOT evidence of improvement; "
        "do not infer recovery from time passed alone).\n\n"
        "Image 1 is the ORIGINAL photo. Image 2 is the NEW photo.\n\n"
        "Rules:\n"
        "- Compare the two images directly. For EACH claimed change, cite which image "
        "and which region (e.g. 'Image 2, lower-left leaf cluster').\n"
        "- If you cannot see a visible difference between the two images, set progress "
        "to 'no_visible_change' and leave changes empty.\n"
        "- Do NOT infer improvement from elapsed time alone.\n"
        "- Do NOT assume the plant recovered because care instructions were followed.\n\n"
        "Return JSON only — no markdown, no prose:\n"
        '{"progress":"improving|stable|worsening|no_visible_change",'
        '"changes":["Image N, <region>: <what changed> vs Image 1 same region", ...],'
        '"updated_care_plan":"..."}'
    )

    response = _openai_client().chat.completions.create(
        model=_VISION_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime_orig};base64,{b64_orig}"}},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime_new};base64,{b64_new}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        temperature=0.2,
        max_tokens=1024,
    )

    raw = response.choices[0].message.content
    try:
        data = _parse_json(raw)
    except (ValueError, json.JSONDecodeError):
        data = {}

    progress     = data.get("progress", "stable")
    changes      = data.get("changes", [])
    updated_plan = data.get("updated_care_plan", "") or old_plan

    print(f"[followup] progress={progress}, changes={len(changes)}")
    return {
        "progress":  progress,
        "changes":   changes,
        "care_plan": updated_plan,
        "phase":     "done",
    }


# ── routers ───────────────────────────────────────────────────────────────────

def _start_router(state: PlantAgentState) -> str:
    return "followup" if state.get("phase") == "checkin" else "identify_species"


def _after_diagnose_router(state: PlantAgentState) -> str:
    diag       = state.get("diagnosis", {})
    confidence = diag.get("confidence", 0.0)
    category   = diag.get("issue_category", "uncertain")

    if category in _ALWAYS_CLARIFY or confidence < _CONFIDENCE_THRESHOLD:
        print(f"[router] category={category} conf={confidence} → ask_clarifying_questions")
        return "ask_clarifying_questions"

    print(f"[router] category={category} conf={confidence} → prescribe_care_plan (direct)")
    return "prescribe_care_plan"


# ── graph ─────────────────────────────────────────────────────────────────────

def build_graph():
    builder = StateGraph(PlantAgentState)

    builder.add_node("identify_species",         identify_species_node)
    builder.add_node("diagnose",                 diagnose_node)
    builder.add_node("ask_clarifying_questions", ask_clarifying_questions_node)
    builder.add_node("prescribe_care_plan",      prescribe_care_plan_node)
    builder.add_node("followup",                 followup_node)

    # conditional entry: normal diagnosis vs. checkin
    builder.add_conditional_edges(START, _start_router, {
        "identify_species": "identify_species",
        "followup":         "followup",
    })

    # normal flow: identify → diagnose → (route by confidence/category)
    builder.add_edge("identify_species", "diagnose")
    builder.add_conditional_edges("diagnose", _after_diagnose_router, {
        "ask_clarifying_questions": "ask_clarifying_questions",
        "prescribe_care_plan":      "prescribe_care_plan",
    })
    builder.add_edge("ask_clarifying_questions", "prescribe_care_plan")
    builder.add_edge("prescribe_care_plan",      END)

    # checkin flow
    builder.add_edge("followup", END)

    return builder.compile(checkpointer=checkpointer)


plant_graph = build_graph()
