"""SQLite connections. The catalog is opened read-only: the agent can never alter store data."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class CatalogNotBuiltError(RuntimeError):
    pass


def connect_catalog(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise CatalogNotBuiltError(
            f"{db_path} not found. Build it with: uv run python tools/prepare_data.py --apply"
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def connect_writable(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
