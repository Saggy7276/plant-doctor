from dotenv import load_dotenv
load_dotenv()  # must run before any module reads os.getenv

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from alembic.config import Config
from alembic import command
from routers import auth, plants, diagnose, knowledge

app = FastAPI(title="Plant Doctor API")


@app.on_event("startup")
def run_migrations():
    cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "alembic"))
    command.upgrade(cfg, "head")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,      prefix="/auth",      tags=["auth"])
app.include_router(plants.router,    prefix="/plants",    tags=["plants"])
app.include_router(diagnose.router,  prefix="/diagnose",  tags=["diagnose"])
app.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])

_upload_dir = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(_upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_upload_dir), name="uploads")


@app.get("/")
def root():
    return {"message": "Plant Doctor API is running"}
