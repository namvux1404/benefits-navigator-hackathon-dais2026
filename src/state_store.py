from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from .config import SQLITE_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    raw_text      TEXT,
    profile_json  TEXT,
    plan_text     TEXT,
    plan_method   TEXT,
    district_norm TEXT,
    state_norm    TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id            TEXT PRIMARY KEY,
    session_id    TEXT,
    created_at    TEXT NOT NULL,
    rating        TEXT NOT NULL,
    comment       TEXT
);
"""


class StateStore:
    def __init__(self, path: Path = SQLITE_PATH):
        self._path = str(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN lineage_json TEXT")
            except Exception:
                pass  # column already exists

    def save_session(
        self,
        raw_text: str,
        profile: dict,
        plan_text: str,
        plan_method: str,
        district_norm: str = "",
        state_norm: str = "",
        lineage: dict | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions "
                "(id, created_at, raw_text, profile_json, plan_text, plan_method, "
                "district_norm, state_norm, lineage_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    now,
                    raw_text,
                    json.dumps(profile, default=str),
                    plan_text,
                    plan_method,
                    district_norm,
                    state_norm,
                    json.dumps(lineage, default=str) if lineage else None,
                ),
            )
        return session_id

    def get_recent_sessions(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_feedback(
        self,
        session_id: str | None,
        rating: str,
        comment: str = "",
    ) -> str:
        feedback_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO feedback (id, session_id, created_at, rating, comment) "
                "VALUES (?, ?, ?, ?, ?)",
                (feedback_id, session_id, now, rating, comment),
            )
        return feedback_id

    def get_recent_feedback(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
