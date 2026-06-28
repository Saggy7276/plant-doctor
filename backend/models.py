from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    plants = relationship("Plant", back_populates="owner")
    photos = relationship("Photo", back_populates="user")
    diagnoses = relationship("Diagnosis", back_populates="user")
    care_plans = relationship("CarePlan", back_populates="user")


class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    species = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="plants")
    photos = relationship("Photo", back_populates="plant")
    diagnoses = relationship("Diagnosis", back_populates="plant")
    care_plans = relationship("CarePlan", back_populates="plant")


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    plant = relationship("Plant", back_populates="photos")
    user = relationship("User", back_populates="photos")
    diagnoses = relationship("Diagnosis", back_populates="photo")


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, index=True)
    image_path = Column(String, nullable=False)
    photo_id = Column(Integer, ForeignKey("photos.id"), nullable=True)
    result = Column(Text)
    confidence = Column(Float)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    thread_id = Column(String, nullable=True)   # LangGraph thread; enables weekly check-ins
    created_at = Column(DateTime, default=datetime.utcnow)

    photo = relationship("Photo", back_populates="diagnoses")
    plant = relationship("Plant", back_populates="diagnoses")
    user = relationship("User", back_populates="diagnoses")
    care_plan = relationship("CarePlan", back_populates="diagnosis", uselist=False)


class CarePlan(Base):
    __tablename__ = "care_plans"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    diagnosis_id = Column(Integer, ForeignKey("diagnoses.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plant = relationship("Plant", back_populates="care_plans")
    user = relationship("User", back_populates="care_plans")
    diagnosis = relationship("Diagnosis", back_populates="care_plan")
