"""SQLite storage for documents, their extraction, validation, human corrections and step events."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL,
    path        TEXT NOT NULL,
    kind        TEXT,
    pages       INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'new',   -- new | processing | auto_approved | needs_review | approved | rejected | failed
    extracted   TEXT,
    validation  TEXT,
    corrected   TEXT,
    cost_usd    REAL NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL DEFAULT 0,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ts          TEXT NOT NULL,
    step        TEXT NOT NULL,
    status      TEXT NOT NULL,
    detail      TEXT,
    duration_ms REAL NOT NULL DEFAULT 0,
    cost_usd    REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_doc ON events(doc_id);
"""
JSON_COLS = ("extracted", "validation", "corrected")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: Path | str) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for c in JSON_COLS:
        if d.get(c):
            d[c] = json.loads(d[c])
    return d


def get_doc(conn, doc_id: int) -> dict | None:
    return to_dict(conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone())


def update_doc(conn, doc_id: int, **fields) -> None:
    for c in JSON_COLS:
        if c in fields and fields[c] is not None and not isinstance(fields[c], str):
            fields[c] = json.dumps(fields[c], ensure_ascii=False)
    fields["updated_at"] = now_iso()
    conn.execute(f"UPDATE documents SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", (*fields.values(), doc_id))
    conn.commit()


def log_event(conn, doc_id: int, step: str, status: str, detail: str = "", ms: float = 0.0, cost: float = 0.0) -> None:
    conn.execute("INSERT INTO events (doc_id, ts, step, status, detail, duration_ms, cost_usd) VALUES (?,?,?,?,?,?,?)",
                 (doc_id, now_iso(), step, status, detail[:500], round(ms, 1), round(cost, 6)))
    conn.commit()


def events_for(conn, doc_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM events WHERE doc_id = ? ORDER BY id", (doc_id,))]
