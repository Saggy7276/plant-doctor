# Single SQLite checkpointer shared across the app.
# LangGraph needs this to save and resume graph state between requests.

import sqlite3
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver

_DB_PATH = str(Path(__file__).parent.parent / "checkpoints.db")

# check_same_thread=False required for FastAPI's thread pool
_conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
checkpointer = SqliteSaver(_conn)
