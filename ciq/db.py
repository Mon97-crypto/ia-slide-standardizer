"""Store for the shared competitor library.

Two backends, one API:

  SQLite    default, zero setup, good for local work. Full text via FTS5.
  Postgres  set DATABASE_URL. Full text via tsvector with weighted ts_rank_cd.

Postgres is what makes the library permanent on a host with an ephemeral
filesystem. A managed database survives deploys, restarts and instance moves,
none of which a container-local SQLite file does.

Ranking is deliberately equivalent across both: the competitor and title fields
outrank the note, which outranks the document body, so a passing mention in a
long PDF never beats a real title match.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

from .competitors import canonical_name, competitor_key

_local = threading.local()

ENTRY_FIELDS = (
    "id", "competitor", "competitor_key", "title", "category", "note",
    "lovable_url", "file_url", "file_name", "source_kind", "content",
    "content_chars", "extract_status", "analysis_json", "analyzed_at",
    "created_at", "updated_at",
)

# Field weights. Postgres labels are A/B/C/D; SQLite takes explicit numbers.
# Both express the same ordering: competitor and title, then note, then body.
PG_WEIGHTS = "{0.1, 0.2, 0.4, 1.0}"          # D, C, B, A
SQLITE_WEIGHTS = "0.0, 8.0, 6.0, 3.0, 1.0"   # entry_id, competitor, title, note, content

SQLITE_SCHEMA = """
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
    entry_id UNINDEXED, competitor, title, note, content,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED, entry_id UNINDEXED, text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

# Generated tsvector columns keep the index correct without triggers or any
# application-side sync, so the index cannot drift from the rows.
POSTGRES_SCHEMA = """
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
    updated_at     TEXT NOT NULL,
    search_vector  tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(competitor, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(note, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(content, '')), 'D')
    ) STORED
);
CREATE INDEX IF NOT EXISTS idx_entries_competitor ON entries(competitor_key);
CREATE INDEX IF NOT EXISTS idx_entries_category   ON entries(category);
CREATE INDEX IF NOT EXISTS idx_entries_created    ON entries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_entries_search     ON entries USING GIN(search_vector);

CREATE TABLE IF NOT EXISTS chunks (
    id       BIGSERIAL PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    ord      INTEGER NOT NULL,
    text     TEXT NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(text, ''))
    ) STORED
);
CREATE INDEX IF NOT EXISTS idx_chunks_entry  ON chunks(entry_id);
CREATE INDEX IF NOT EXISTS idx_chunks_search ON chunks USING GIN(search_vector);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """A database connection plus the dialect needed to talk to it."""

    def __init__(self, conn, dialect: str):
        self.conn = conn
        self.dialect = dialect

    @property
    def is_postgres(self) -> bool:
        return self.dialect == "postgres"

    def execute(self, sql: str, params: Iterable[Any] = ()):
        """Run a statement, translating '?' placeholders for Postgres."""
        if self.is_postgres:
            sql = sql.replace("?", "%s")
        cur = self.conn.cursor()
        cur.execute(sql, tuple(params))
        return cur

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


def _is_postgres_url(url: str) -> bool:
    return urlparse(url).scheme in ("postgres", "postgresql")


def connect(target: str) -> Store:
    """Open (or reuse) a per-thread connection.

    `target` is a DATABASE_URL for Postgres or a file path for SQLite.
    Flask serves requests on several threads, and neither driver's connections
    are safe to share across them.
    """
    cached = getattr(_local, "store", None)
    if cached is not None and getattr(_local, "target", None) == target:
        return cached

    if _is_postgres_url(target):
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(target, row_factory=dict_row, autocommit=False)
        store = Store(conn, "postgres")
        with conn.cursor() as cur:
            cur.execute(POSTGRES_SCHEMA)
        conn.commit()
    else:
        os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)
        conn = sqlite3.connect(target, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SQLITE_SCHEMA)
        conn.commit()
        store = Store(conn, "sqlite")

    _local.store, _local.target = store, target
    return store


def row_to_dict(row) -> dict[str, Any] | None:
    """Normalise a driver row into a plain dict, parsing stored analysis."""
    if row is None:
        return None
    entry = dict(row) if not isinstance(row, sqlite3.Row) else {
        k: row[k] for k in row.keys()}
    entry.pop("search_vector", None)
    raw = entry.pop("analysis_json", "") or ""
    try:
        entry["analysis"] = json.loads(raw) if raw else None
    except (json.JSONDecodeError, TypeError):
        entry["analysis"] = None
    return entry


# ─── full text ─────────────────────────────────────────────────────────────

def sanitise_terms(terms: Iterable[str]) -> list[str]:
    """Strip anything that could break a full-text query in either dialect."""
    cleaned = []
    for term in terms:
        safe = re.sub(r"[^0-9a-z]+", "", (term or "").lower())
        if safe:
            cleaned.append(safe)
    return cleaned


def _fts5_query(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"*' for t in terms)


def _tsquery(terms: list[str]) -> str:
    return " | ".join(f"{t}:*" for t in terms)


def text_scores(store: Store, terms: list[str], limit: int = 500) -> dict[str, float]:
    """Relevance per entry for the given terms. Higher is a better match."""
    terms = sanitise_terms(terms)
    if not terms:
        return {}

    if store.is_postgres:
        rows = store.execute(
            f"SELECT id, ts_rank_cd('{PG_WEIGHTS}', search_vector,"
            " to_tsquery('english', ?)) AS score"
            " FROM entries WHERE search_vector @@ to_tsquery('english', ?)"
            " ORDER BY score DESC LIMIT ?",
            (_tsquery(terms), _tsquery(terms), limit),
        ).fetchall()
        return {r["id"]: float(r["score"]) for r in rows}

    rows = store.execute(
        f"SELECT entry_id, bm25(entries_fts, {SQLITE_WEIGHTS}) AS score"
        " FROM entries_fts WHERE entries_fts MATCH ?"
        " ORDER BY score LIMIT ?",
        (_fts5_query(terms), limit),
    ).fetchall()
    # bm25() is negative, with more negative meaning a better match.
    return {r["entry_id"]: -float(r["score"]) for r in rows}


def passage_scores(store: Store, terms: list[str], entry_id: str = "",
                   competitor_key_value: str = "",
                   limit: int = 8) -> list[dict[str, Any]]:
    """Best-matching passages, optionally scoped to one entry or competitor."""
    terms = sanitise_terms(terms)
    if not terms:
        return []

    if store.is_postgres:
        clauses = ["c.search_vector @@ to_tsquery('english', ?)"]
        params: list[Any] = [_tsquery(terms), _tsquery(terms)]
        # The rank expression also needs the query, so it is bound first.
        sql_head = ("SELECT c.entry_id, c.text,"
                    " ts_rank_cd(c.search_vector, to_tsquery('english', ?)) AS score,"
                    " e.title, e.competitor, e.category"
                    " FROM chunks c JOIN entries e ON e.id = c.entry_id WHERE ")
        params = [_tsquery(terms), _tsquery(terms)]
        if entry_id:
            clauses.append("c.entry_id = ?")
            params.append(entry_id)
        elif competitor_key_value:
            clauses.append("e.competitor_key = ?")
            params.append(competitor_key_value)
        params.append(limit)
        rows = store.execute(
            sql_head + " AND ".join(clauses) + " ORDER BY score DESC LIMIT ?",
            params).fetchall()
        return [{
            "entry_id": r["entry_id"], "title": r["title"],
            "competitor": r["competitor"], "category": r["category"],
            "text": r["text"], "score": round(float(r["score"]), 4),
        } for r in rows]

    clauses = ["chunks_fts MATCH ?"]
    params = [_fts5_query(terms)]
    if entry_id:
        clauses.append("c.entry_id = ?")
        params.append(entry_id)
    elif competitor_key_value:
        clauses.append("e.competitor_key = ?")
        params.append(competitor_key_value)
    params.append(limit)
    rows = store.execute(
        "SELECT c.entry_id, c.text, bm25(chunks_fts) AS score,"
        " e.title, e.competitor, e.category"
        " FROM chunks_fts c JOIN entries e ON e.id = c.entry_id"
        f" WHERE {' AND '.join(clauses)} ORDER BY score LIMIT ?",
        params).fetchall()
    return [{
        "entry_id": r["entry_id"], "title": r["title"],
        "competitor": r["competitor"], "category": r["category"],
        "text": r["text"], "score": round(-float(r["score"]), 4),
    } for r in rows]


# ─── writes ────────────────────────────────────────────────────────────────

def _index_entry(store: Store, entry_id: str, competitor: str, title: str,
                 note: str, content: str) -> None:
    """Refresh the entry's full-text row. Postgres maintains its own."""
    if store.is_postgres:
        return
    store.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))
    store.execute(
        "INSERT INTO entries_fts (entry_id, competitor, title, note, content)"
        " VALUES (?, ?, ?, ?, ?)",
        (entry_id, competitor, title, note, content))


def _index_chunks(store: Store, entry_id: str, chunks: Iterable[str]) -> None:
    if not store.is_postgres:
        store.execute("DELETE FROM chunks_fts WHERE entry_id = ?", (entry_id,))
    store.execute("DELETE FROM chunks WHERE entry_id = ?", (entry_id,))
    for ordinal, text in enumerate(chunks):
        if store.is_postgres:
            store.execute(
                "INSERT INTO chunks (entry_id, ord, text) VALUES (?, ?, ?)",
                (entry_id, ordinal, text))
            continue
        cur = store.execute(
            "INSERT INTO chunks (entry_id, ord, text) VALUES (?, ?, ?)",
            (entry_id, ordinal, text))
        store.execute(
            "INSERT INTO chunks_fts (chunk_id, entry_id, text) VALUES (?, ?, ?)",
            (cur.lastrowid, entry_id, text))


def create_entry(store: Store, data: dict[str, Any],
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
    store.execute(
        f"INSERT INTO entries ({', '.join(ENTRY_FIELDS)}) VALUES ({placeholders})",
        tuple(record[f] for f in ENTRY_FIELDS))
    _index_entry(store, entry_id, record["competitor"], record["title"],
                 record["note"], record["content"])
    _index_chunks(store, entry_id, chunks)
    store.commit()
    return get_entry(store, entry_id)


def update_entry(store: Store, entry_id: str,
                 fields: dict[str, Any]) -> dict[str, Any] | None:
    current = store.execute(
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
    store.execute(f"UPDATE entries SET {assignments} WHERE id = ?",
                  (*allowed.values(), entry_id))
    merged = store.execute(
        "SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    merged = row_to_dict(merged)
    _index_entry(store, entry_id, merged["competitor"], merged["title"],
                 merged["note"], merged["content"])
    store.commit()
    return get_entry(store, entry_id)


def set_chunks(store: Store, entry_id: str, chunks: Iterable[str]) -> None:
    _index_chunks(store, entry_id, chunks)
    store.commit()


def delete_entry(store: Store, entry_id: str) -> bool:
    cur = store.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    deleted = cur.rowcount > 0
    if not store.is_postgres:
        store.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))
        store.execute("DELETE FROM chunks_fts WHERE entry_id = ?", (entry_id,))
        store.execute("DELETE FROM chunks WHERE entry_id = ?", (entry_id,))
    store.commit()
    return deleted


def clear_all(store: Store) -> int:
    total = store.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"]
    tables = ("entries", "chunks") if store.is_postgres else (
        "entries", "entries_fts", "chunks", "chunks_fts")
    for table in tables:
        store.execute(f"DELETE FROM {table}")
    store.commit()
    return total


# ─── reads ─────────────────────────────────────────────────────────────────

def get_entry(store: Store, entry_id: str) -> dict[str, Any] | None:
    return row_to_dict(store.execute(
        "SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone())


def list_entries(store: Store, category: str = "", competitor: str = "",
                 limit: int = 500) -> list[dict[str, Any]]:
    clauses, params = [], []
    if category and category != "all":
        clauses.append("category = ?")
        params.append(category)
    if competitor:
        clauses.append("competitor_key = ?")
        params.append(competitor_key(competitor))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = store.execute(
        f"SELECT * FROM entries {where} ORDER BY created_at DESC LIMIT ?",
        (*params, limit)).fetchall()
    return [row_to_dict(r) for r in rows]


def entries_where(store: Store, category: str = "",
                  competitor_key_value: str = "") -> list[dict[str, Any]]:
    clauses, params = [], []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if competitor_key_value:
        clauses.append("competitor_key = ?")
        params.append(competitor_key_value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = store.execute(f"SELECT * FROM entries {where}", params).fetchall()
    return [row_to_dict(r) for r in rows]


def chunks_for(store: Store, entry_id: str) -> list[str]:
    rows = store.execute(
        "SELECT text FROM chunks WHERE entry_id = ? ORDER BY ord",
        (entry_id,)).fetchall()
    return [r["text"] for r in rows]


def stats(store: Store) -> dict[str, Any]:
    total = store.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"]
    by_cat = {r["category"]: r["n"] for r in store.execute(
        "SELECT category, COUNT(*) AS n FROM entries GROUP BY category").fetchall()}
    competitors = store.execute(
        "SELECT COUNT(DISTINCT competitor_key) AS n FROM entries"
        " WHERE competitor_key <> ''").fetchone()["n"]
    analysed = store.execute(
        "SELECT COUNT(*) AS n FROM entries WHERE analysis_json <> ''"
    ).fetchone()["n"]
    indexed = store.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    return {
        "entries": total, "competitors": competitors, "by_category": by_cat,
        "analysed": analysed, "chunks": indexed, "backend": store.dialect,
    }
