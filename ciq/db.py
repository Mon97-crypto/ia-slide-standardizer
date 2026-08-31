"""SQLite store for the shared competitor library.

One database file, one source of truth. Every teammate hitting this server sees
the same library, which is the whole point: a browser-local library is not a
shared library.

Two FTS5 indexes are maintained alongside the tables:
  entries_fts  ranks whole entries for the search box
  chunks_fts   retrieves passages for grounded question answering
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from .competitors import canonical_name, competitor_key

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id             TEXT PRIMARY KEY,
    competitor     TEXT NOT NULL DEFAULT '',
    competitor_key TEXT NOT NULL DEFAULT '',
    title          TEXT NOT NULL DEFAULT '',
    category       TEXT NOT NULL DEFAULT 'information',
    note           TEXT NOT NULL DEFAULT '',
    lovable_url    TEXT NOT NULL DEFAULT '',
    file_url       TEXT NOT NULL DEFAULT '',
    file_name      TEXT NOT NULL DEFAULT '',
    source_kind    TEXT NOT NULL DEFAULT '',
    content        TEXT NOT NULL DEFAULT '',
    content_chars  INTEGER NOT NULL DEFAULT 0,
    extract_status TEXT NOT NULL DEFAULT '',
    analysis_json  TEXT NOT NULL DEFAULT '',
    analyzed_at    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_competitor ON entries(competitor_key);
CREATE INDEX IF NOT EXISTS idx_entries_category   ON entries(category);
CREATE INDEX IF NOT EXISTS idx_entries_created    ON entries(created_at DESC);

CREATE TABLE IF NOT EXISTS chunks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    ord      INTEGER NOT NULL,
    text     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_entry ON chunks(entry_id);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    entry_id UNINDEXED,
    competitor,
    title,
    note,
    content,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    entry_id UNINDEXED,
    text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

ENTRY_FIELDS = (
    "id", "competitor", "competitor_key", "title", "category", "note",
    "lovable_url", "file_url", "file_name", "source_kind", "content",
    "content_chars", "extract_status", "analysis_json", "analyzed_at",
    "created_at", "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str) -> sqlite3.Connection:
    """Per-thread connection. Flask serves requests on several threads."""
    cached = getattr(_local, "conn", None)
    if cached is not None and getattr(_local, "path", None) == db_path:
        return cached
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    _local.conn, _local.path = conn, db_path
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    entry = {k: row[k] for k in row.keys()}
    raw = entry.pop("analysis_json", "") or ""
    try:
        entry["analysis"] = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        entry["analysis"] = None
    return entry


# ─── writes ────────────────────────────────────────────────────────────────

def _index_entry(conn: sqlite3.Connection, entry_id: str, competitor: str,
                 title: str, note: str, content: str) -> None:
    conn.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))
    conn.execute(
        "INSERT INTO entries_fts (entry_id, competitor, title, note, content)"
        " VALUES (?, ?, ?, ?, ?)",
        (entry_id, competitor, title, note, content),
    )


def _index_chunks(conn: sqlite3.Connection, entry_id: str,
                  chunks: Iterable[str]) -> None:
    conn.execute("DELETE FROM chunks_fts WHERE entry_id = ?", (entry_id,))
    conn.execute("DELETE FROM chunks WHERE entry_id = ?", (entry_id,))
    for ordinal, text in enumerate(chunks):
        cur = conn.execute(
            "INSERT INTO chunks (entry_id, ord, text) VALUES (?, ?, ?)",
            (entry_id, ordinal, text),
        )
        conn.execute(
            "INSERT INTO chunks_fts (chunk_id, entry_id, text) VALUES (?, ?, ?)",
            (cur.lastrowid, entry_id, text),
        )


def create_entry(conn: sqlite3.Connection, data: dict[str, Any],
                 chunks: Iterable[str] = ()) -> dict[str, Any]:
    entry_id = data.get("id") or uuid.uuid4().hex[:12]
    competitor = canonical_name(data.get("competitor", ""))
    now = _now()
    record = {
        "id": entry_id,
        "competitor": competitor,
        "competitor_key": competitor_key(competitor),
        "title": (data.get("title") or "").strip(),
        "category": data.get("category") or "information",
        "note": (data.get("note") or "").strip(),
        "lovable_url": (data.get("lovable_url") or "").strip(),
        "file_url": (data.get("file_url") or "").strip(),
        "file_name": (data.get("file_name") or "").strip(),
        "source_kind": data.get("source_kind") or "",
        "content": data.get("content") or "",
        "content_chars": len(data.get("content") or ""),
        "extract_status": data.get("extract_status") or "",
        "analysis_json": data.get("analysis_json") or "",
        "analyzed_at": data.get("analyzed_at") or "",
        "created_at": data.get("created_at") or now,
        "updated_at": now,
    }
    placeholders = ", ".join("?" for _ in ENTRY_FIELDS)
    conn.execute(
        f"INSERT INTO entries ({', '.join(ENTRY_FIELDS)}) VALUES ({placeholders})",
        tuple(record[f] for f in ENTRY_FIELDS),
    )
    _index_entry(conn, entry_id, record["competitor"], record["title"],
                 record["note"], record["content"])
    _index_chunks(conn, entry_id, chunks)
    conn.commit()
    return get_entry(conn, entry_id)


def update_entry(conn: sqlite3.Connection, entry_id: str,
                 fields: dict[str, Any]) -> dict[str, Any] | None:
    current = conn.execute(
        "SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    if current is None:
        return None
    allowed = {k: v for k, v in fields.items()
               if k in ENTRY_FIELDS and k not in ("id", "created_at")}
    if "competitor" in allowed:
        allowed["competitor"] = canonical_name(allowed["competitor"])
        allowed["competitor_key"] = competitor_key(allowed["competitor"])
    if "content" in allowed:
        allowed["content_chars"] = len(allowed["content"] or "")
    allowed["updated_at"] = _now()

    assignments = ", ".join(f"{k} = ?" for k in allowed)
    conn.execute(f"UPDATE entries SET {assignments} WHERE id = ?",
                 (*allowed.values(), entry_id))
    merged = conn.execute(
        "SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    _index_entry(conn, entry_id, merged["competitor"], merged["title"],
                 merged["note"], merged["content"])
    conn.commit()
    return get_entry(conn, entry_id)


def set_chunks(conn: sqlite3.Connection, entry_id: str,
               chunks: Iterable[str]) -> None:
    _index_chunks(conn, entry_id, chunks)
    conn.commit()


def delete_entry(conn: sqlite3.Connection, entry_id: str) -> bool:
    cur = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))
    conn.execute("DELETE FROM chunks_fts WHERE entry_id = ?", (entry_id,))
    conn.execute("DELETE FROM chunks WHERE entry_id = ?", (entry_id,))
    conn.commit()
    return cur.rowcount > 0


def clear_all(conn: sqlite3.Connection) -> int:
    total = conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"]
    for table in ("entries", "entries_fts", "chunks", "chunks_fts"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    return total


# ─── reads ─────────────────────────────────────────────────────────────────

def get_entry(conn: sqlite3.Connection, entry_id: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone())


def list_entries(conn: sqlite3.Connection, category: str = "",
                 competitor: str = "", limit: int = 500) -> list[dict[str, Any]]:
    clauses, params = [], []
    if category and category != "all":
        clauses.append("category = ?")
        params.append(category)
    if competitor:
        clauses.append("competitor_key = ?")
        params.append(competitor_key(competitor))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM entries {where} ORDER BY created_at DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def chunks_for(conn: sqlite3.Connection, entry_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT text FROM chunks WHERE entry_id = ? ORDER BY ord", (entry_id,)
    ).fetchall()
    return [r["text"] for r in rows]


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"]
    by_cat = {r["category"]: r["n"] for r in conn.execute(
        "SELECT category, COUNT(*) AS n FROM entries GROUP BY category")}
    competitors = conn.execute(
        "SELECT COUNT(DISTINCT competitor_key) AS n FROM entries"
        " WHERE competitor_key <> ''").fetchone()["n"]
    analysed = conn.execute(
        "SELECT COUNT(*) AS n FROM entries WHERE analysis_json <> ''"
    ).fetchone()["n"]
    indexed = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    return {
        "entries": total,
        "competitors": competitors,
        "by_category": by_cat,
        "analysed": analysed,
        "chunks": indexed,
    }
