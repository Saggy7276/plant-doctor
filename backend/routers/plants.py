from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from typing import List
import os, uuid, shutil
from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")


@router.post("/", response_model=schemas.PlantOut, status_code=status.HTTP_201_CREATED)
def create_plant(
    plant_in: schemas.PlantCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    plant = models.Plant(**plant_in.model_dump(), owner_id=current_user.id)
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return plant


@router.get("/", response_model=List[schemas.PlantOut])
def list_plants(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return db.query(models.Plant).filter(models.Plant.owner_id == current_user.id).all()


@router.get("/{plant_id}", response_model=schemas.PlantOut)
def get_plant(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    plant = db.query(models.Plant).filter(
        models.Plant.id == plant_id, models.Plant.owner_id == current_user.id
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return plant


@router.put("/{plant_id}", response_model=schemas.PlantOut)
def update_plant(
    plant_id: int,
    plant_in: schemas.PlantUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    plant = db.query(models.Plant).filter(
        models.Plant.id == plant_id, models.Plant.owner_id == current_user.id
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    update_data = plant_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(plant, field, value)
    db.commit()
    db.refresh(plant)
    return plant


@router.post("/{plant_id}/photos", response_model=schemas.PhotoOut, status_code=status.HTTP_201_CREATED)
def upload_photo(
    plant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    plant = db.query(models.Plant).filter(
        models.Plant.id == plant_id, models.Plant.owner_id == current_user.id
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")

    ext = os.path.splitext(file.filename or "")[-1].lower() or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest_dir = os.path.join(UPLOAD_DIR, str(current_user.id), str(plant_id))
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    photo = models.Photo(
        filename=dest_path,
        original_filename=file.filename,
        plant_id=plant_id,
        user_id=current_user.id,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


@router.get("/{plant_id}/photos", response_model=List[schemas.PhotoOut])
def list_photos(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    plant = db.query(models.Plant).filter(
        models.Plant.id == plant_id, models.Plant.owner_id == current_user.id
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return (
        db.query(models.Photo)
        .filter(models.Photo.plant_id == plant_id)
        .order_by(models.Photo.uploaded_at.desc())
        .all()
    )


@router.delete("/{plant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plant(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    plant = db.query(models.Plant).filter(
        models.Plant.id == plant_id, models.Plant.owner_id == current_user.id
    ).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    # Delete child records in FK-safe order: care_plans → diagnoses → photos → plant
    db.query(models.CarePlan).filter(models.CarePlan.plant_id == plant_id).delete()
    db.query(models.Diagnosis).filter(models.Diagnosis.plant_id == plant_id).delete()
    db.query(models.Photo).filter(models.Photo.plant_id == plant_id).delete()
    db.delete(plant)
    db.commit()
