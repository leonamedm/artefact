"""Conversation history and human hand-offs (see ADR-0005). Separate DB from the catalog,
because the catalog is regenerated from the sources and must stay read-only."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    seq        INTEGER NOT NULL,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    reason     TEXT NOT NULL,
    summary    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class ConversationRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.executescript(SCHEMA)

    def create_session(self, now: datetime) -> str:
        session_id = uuid.uuid4().hex[:12]
        with self._conn:
            self._conn.execute("INSERT INTO sessions VALUES (?, ?)", (session_id, now.isoformat()))
        return session_id

    def exists(self, session_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row is not None

    def load(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT payload FROM messages WHERE session_id = ? ORDER BY seq", (session_id,)
        )
        return [json.loads(r["payload"]) for r in rows]

    def append(self, session_id: str, messages: list[dict[str, Any]], now: datetime) -> None:
        with self._conn:
            start = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM messages WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
            self._conn.executemany(
                "INSERT INTO messages VALUES (?, ?, ?, ?)",
                [
                    (session_id, start + i, json.dumps(m, ensure_ascii=False), now.isoformat())
                    for i, m in enumerate(messages, start=1)
                ],
            )

    def record_handoff(
        self, session_id: str | None, reason: str, summary: str, now: datetime
    ) -> int:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO handoffs (session_id, reason, summary, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, reason, summary, now.isoformat()),
            )
        return int(cursor.lastrowid)
