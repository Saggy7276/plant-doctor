from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
import models
import rag_service

router = APIRouter()


class IngestIn(BaseModel):
    text:   str
    source: str
    topic:  str = ""


@router.post("/ingest")
def ingest(body: IngestIn, current_user: models.User = Depends(get_current_user)):
    if not body.text.strip():
        raise HTTPException(400, "Text cannot be empty")
    if not body.source.strip():
        raise HTTPException(400, "Source name is required")
    n = rag_service.ingest(body.text.strip(), body.source.strip(), body.topic.strip())
    return {"chunks_stored": n, "source": body.source}


@router.get("/sources")
def list_sources(current_user: models.User = Depends(get_current_user)):
    return rag_service.list_sources()


@router.delete("/sources/{source:path}")
def delete_source(source: str, current_user: models.User = Depends(get_current_user)):
    n = rag_service.delete_source(source)
    if n == 0:
        raise HTTPException(404, f"Source '{source}' not found")
    return {"deleted_chunks": n}
