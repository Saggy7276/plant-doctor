# Plant Doctor — Backend

FastAPI REST API that handles authentication, plant management, the diagnosis agent, and the knowledge base.

---

## Structure

```
backend/
├── main.py             # FastAPI app, middleware, router registration, Alembic startup hook
├── database.py         # SQLAlchemy engine + session factory
├── models.py           # ORM models (User, Plant, Photo, Diagnosis, CarePlan)
├── schemas.py          # Pydantic request/response schemas
├── auth.py             # JWT creation and verification, password hashing
├── vision_service.py   # GPT-4o calls for species identification and visual diagnosis
├── rag_service.py      # ChromaDB ingest and retrieval
├── routers/
│   ├── auth.py         # POST /auth/register, POST /auth/login
│   ├── plants.py       # CRUD for /plants/
│   ├── diagnose.py     # Diagnosis agent endpoints
│   └── knowledge.py    # Knowledge base endpoints
└── alembic/            # Database migration scripts
```

---

## Running

```bash
cd backend
uvicorn main:app --reload
```

Migrations run automatically on startup. Interactive docs are at `http://localhost:8000/docs`.

---

## API endpoints

### Auth — `/auth`

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create a new account |
| POST | `/auth/login` | Return a JWT access token |

### Plants — `/plants`

| Method | Path | Description |
|---|---|---|
| GET | `/plants/` | List all plants for the current user |
| POST | `/plants/` | Add a new plant |
| GET | `/plants/{id}` | Get a single plant |
| PUT | `/plants/{id}` | Update name / species |
| DELETE | `/plants/{id}` | Delete a plant and cascade-remove all its diagnoses, care plans, and photos |

### Diagnose — `/diagnose`

| Method | Path | Description |
|---|---|---|
| POST | `/diagnose/{plant_id}` | Upload a photo and start the diagnosis agent |
| POST | `/diagnose/{plant_id}/resume` | Resume a paused agent with the user's answers |
| POST | `/diagnose/{plant_id}/checkin` | 7-day check-in: compare new photo with original |
| GET | `/diagnose/history` | All past diagnoses for the current user |
| GET | `/diagnose/{plant_id}/latest-care-plan` | Most recent care plan for a plant |
| GET | `/diagnose/{plant_id}/latest-thread` | `thread_id` + image path of the last completed diagnosis |

### Knowledge — `/knowledge`

| Method | Path | Description |
|---|---|---|
| POST | `/knowledge/ingest` | Chunk, embed, and store text in ChromaDB |
| GET | `/knowledge/sources` | List all sources with chunk counts |
| DELETE | `/knowledge/sources/{source}` | Remove a source and all its chunks |

---

## Diagnosis agent flow

The agent (`agent/graph.py`) is a LangGraph state machine with these nodes:

```
START
  │
  ├─ (phase == "checkin") ──► followup_node ──► END
  │
  └─ identify_species_node
         │
         ▼
     diagnose_node
         │
         ├─ (low confidence or ambiguous) ──► ask_clarifying_questions_node
         │                                          │
         │                                          ▼
         └─ (high confidence) ──────────► prescribe_care_plan_node ──► END
```

- **identify_species_node** — calls GPT-4o vision to name the plant species.
- **diagnose_node** — calls GPT-4o vision to identify the issue and return a confidence score.
- **ask_clarifying_questions_node** — generates 2–3 questions and pauses the graph with `interrupt()` until the user answers.
- **prescribe_care_plan_node** — retrieves relevant chunks from ChromaDB, then calls GPT-4o-mini to write the care plan.
- **followup_node** — sends both images to GPT-4o and returns a progress label + updated care plan.

The graph checkpoint is persisted in `checkpoints.db` (project root). The `thread_id` saved on each `Diagnosis` row is the key used to reload or resume the agent later.

---

## Authentication

All endpoints except `/auth/register` and `/auth/login` require a `Bearer` token in the `Authorization` header. Tokens are signed HS256 JWTs with a 24-hour expiry. The secret comes from `SECRET_KEY` in `.env`.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./plant_doctor.db` | SQLAlchemy connection string |
| `SECRET_KEY` | — | JWT signing key (required) |
| `UPLOAD_DIR` | `uploads` | Directory where uploaded images are saved |
| `OPENAI_API_KEY` | — | Required for GPT-4o and embeddings |

---

## Key dependencies

| Package | Used for |
|---|---|
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server |
| `sqlalchemy` | ORM |
| `alembic` | Database migrations |
| `python-jose` | JWT encoding/decoding |
| `passlib[bcrypt]` | Password hashing |
| `langgraph` | Agent state machine |
| `openai` | GPT-4o vision + text + embeddings |
| `chromadb` | Local vector store |
| `python-multipart` | File upload support |
