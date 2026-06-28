"""
rag_service.py — ChromaDB-backed plant-care knowledge base.

Public API:
    ingest(text, source, topic)  -> int   (number of chunks stored)
    retrieve(query, n_results)   -> list[dict]  (chunks with citations)
    list_sources()               -> list[dict]
    delete_source(source)        -> int   (chunks deleted)
"""

import os
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

CHROMA_DIR      = str(Path(__file__).parent.parent / "knowledge_db")
COLLECTION_NAME = "plant_care"
CHUNK_SIZE      = 400
CHUNK_OVERLAP   = 50


def _collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_name="text-embedding-3-small",
    )
    return client.get_or_create_collection(COLLECTION_NAME, embedding_function=ef)


def _chunk(text: str) -> list[str]:
    """Split text into overlapping chunks by paragraph, then by sentence."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    for para in paragraphs:
        if len(para) <= CHUNK_SIZE:
            chunks.append(para)
        else:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) + 1 <= CHUNK_SIZE:
                    current = (current + " " + sent).strip()
                else:
                    if current:
                        chunks.append(current)
                    current = sent
            if current:
                chunks.append(current)
    return [c for c in chunks if len(c) > 30]


def ingest(text: str, source: str, topic: str = "") -> int:
    """Chunk and embed text into ChromaDB. Replaces any existing chunks for the source."""
    col    = _collection()
    chunks = _chunk(text)
    if not chunks:
        return 0

    # replace existing chunks for this source
    try:
        existing = col.get(where={"source": source})
        if existing["ids"]:
            col.delete(ids=existing["ids"])
    except Exception:
        pass

    ids       = [f"{source}::{i}" for i in range(len(chunks))]
    metadatas = [{"source": source, "topic": topic, "chunk_index": i}
                 for i in range(len(chunks))]
    col.add(documents=chunks, ids=ids, metadatas=metadatas)
    return len(chunks)


def retrieve(query: str, n_results: int = 4) -> list[dict]:
    """Return top-N relevant chunks with source citations."""
    col = _collection()
    try:
        count = col.count()
        if count == 0:
            return []
        results = col.query(query_texts=[query], n_results=min(n_results, count))
        return [
            {"text": doc, "source": meta.get("source", ""), "topic": meta.get("topic", "")}
            for doc, meta in zip(results["documents"][0], results["metadatas"][0])
        ]
    except Exception:
        return []


def list_sources() -> list[dict]:
    """Return all unique sources with their chunk counts."""
    col = _collection()
    try:
        all_items = col.get()
        sources: dict[str, dict] = {}
        for meta in all_items.get("metadatas", []):
            src = meta.get("source", "")
            if src not in sources:
                sources[src] = {"source": src, "topic": meta.get("topic", ""), "chunks": 0}
            sources[src]["chunks"] += 1
        return list(sources.values())
    except Exception:
        return []


def delete_source(source: str) -> int:
    """Delete all chunks for a given source. Returns number deleted."""
    col = _collection()
    try:
        existing = col.get(where={"source": source})
        ids = existing.get("ids", [])
        if ids:
            col.delete(ids=ids)
        return len(ids)
    except Exception:
        return 0
