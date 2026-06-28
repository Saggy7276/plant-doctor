from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


# --- Auth ---
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# --- Plants ---
class PlantCreate(BaseModel):
    name: str
    species: Optional[str] = None


class PlantUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None


class PlantOut(BaseModel):
    id: int
    name: str
    species: Optional[str]
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Photos ---
class PhotoOut(BaseModel):
    id: int
    filename: str
    original_filename: Optional[str]
    plant_id: Optional[int]
    user_id: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


# --- Diagnosis ---
class DiagnosisOut(BaseModel):
    id: int
    image_path: str
    result: Optional[str]
    confidence: Optional[float]
    plant_id: Optional[int]
    user_id: int
    thread_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LatestThreadOut(BaseModel):
    thread_id: str
    image_path: str


class DiagnoseStartOut(BaseModel):
    thread_id:    str
    questions:    list[str]
    diagnosis:    dict
    # populated only on the direct (no Q&A) path
    completed:    bool = False
    care_plan:    Optional[str] = None
    care_plan_id: Optional[int] = None


class DiagnoseResumeIn(BaseModel):
    thread_id: str
    answers: str


class DiagnoseResumeOut(BaseModel):
    care_plan: str
    diagnosis_id: int
    care_plan_id: int


# --- CarePlan ---
class CarePlanOut(BaseModel):
    id: int
    title: str
    content: str
    plant_id: int
    user_id: int
    diagnosis_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# --- Checkin (7-day follow-up) ---
class CheckinOut(BaseModel):
    progress: str               # improving | stable | worsening
    changes: list[str]
    updated_care_plan: str
    diagnosis_id: int
    care_plan_id: int
    original_image_path: str    # path of the before photo (for side-by-side display)
    new_image_path: str         # path of the after photo
