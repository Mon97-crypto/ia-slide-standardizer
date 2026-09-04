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
from urllib.parse import urlparse, urlsplit

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

CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    feature       TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    user_email    TEXT NOT NULL DEFAULT '',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read    INTEGER NOT NULL DEFAULT 0,
    cache_write   INTEGER NOT NULL DEFAULT 0,
    web_searches  INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts DESC);
CREATE INDEX IF NOT EXISTS idx_usage_feature ON usage(feature);

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

CREATE TABLE IF NOT EXISTS usage (
    id            BIGSERIAL PRIMARY KEY,
    ts            TEXT NOT NULL,
    feature       TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    user_email    TEXT NOT NULL DEFAULT '',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read    INTEGER NOT NULL DEFAULT 0,
    cache_write   INTEGER NOT NULL DEFAULT 0,
    web_searches  INTEGER NOT NULL DEFAULT 0,
    cost_usd      DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts DESC);
CREATE INDEX IF NOT EXISTS idx_usage_feature ON usage(feature);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """A database connection plus the dialect needed to talk to it."""

    def __init__(self, conn, dialect: str, target: str = ""):
        self.conn = conn
        self.dialect = dialect
        self.target = target

    @property
    def is_postgres(self) -> bool:
        return self.dialect == "postgres"

    def alive(self) -> bool:
        if not self.is_postgres:
            return True
        return not (getattr(self.conn, "closed", False)
                    or getattr(self.conn, "broken", False))

    def _reconnect(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
        self.conn = _open_postgres(self.target)

    def execute(self, sql: str, params: Iterable[Any] = ()):
        """Run a statement, translating '?' placeholders for Postgres.

        A managed database drops idle connections, and a cached connection that
        died would otherwise fail every later request until the worker
        restarted. A dropped connection has already rolled back whatever it was
        doing, so reconnecting and retrying once is safe.
        """
        if self.is_postgres:
            sql = sql.replace("?", "%s")
        try:
            cur = self.conn.cursor()
            cur.execute(sql, tuple(params))
            return cur
        except Exception as exc:
            if not (self.is_postgres and _is_connection_error(exc)):
                raise
            self._reconnect()
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


# Characters that must be percent-encoded inside a password. Left raw, they
# terminate the URL early and the username or a password fragment ends up being
# used as the hostname, which fails DNS with a message that names nothing.
RESERVED_IN_PASSWORD = {"@": "%40", "/": "%2F", "?": "%3F",
                        "#": "%23", ":": "%3A", "&": "%26"}


def describe_target(url: str) -> dict[str, Any]:
    """Explain a connection string without ever revealing its password.

    A DNS failure says only "Name or service not known" and never names the
    host it tried, so the common causes all look identical. Reporting the host
    that was actually parsed makes a mangled URL obvious at a glance.
    """
    report: dict[str, Any] = {"issues": [], "host": None, "port": None,
                              "user": None, "database": None}
    if not url:
        report["issues"].append("DATABASE_URL is empty.")
        return report

    if url != url.strip():
        report["issues"].append(
            "The value has leading or trailing whitespace. Retype it.")
    cleaned = url.strip()
    if cleaned[:1] in ("\"", "'") or cleaned[-1:] in ("\"", "'"):
        report["issues"].append(
            "The value is wrapped in quotes. Save it without them.")
        cleaned = cleaned.strip("\"'")
    if "[" in cleaned or "]" in cleaned:
        report["issues"].append(
            "The value still contains a [placeholder]. Replace it, brackets "
            "included, with the real value.")

    try:
        parts = urlsplit(cleaned)
        report["host"] = parts.hostname
        report["port"] = parts.port
        report["user"] = parts.username
        report["database"] = parts.path.lstrip("/") or None
    except ValueError as exc:
        report["issues"].append(f"The value cannot be parsed: {exc}")
        # A parse failure here is nearly always a raw reserved character in the
        # password rather than a genuinely malformed URL, so say so plainly
        # instead of leaving a message about casting a port.
        report["issues"].append(_password_hint())
        # Recover the host by hand so it can still be reported.
        try:
            netloc = cleaned.split("//", 1)[1].split("/", 1)[0]
            report["host"] = netloc.rsplit("@", 1)[-1].split(":", 1)[0] or None
        except IndexError:
            pass
        return report

    host = report["host"]
    if not host:
        report["issues"].append("No host could be read from the value.")
    elif host == report.get("user"):
        # The unmistakable signature of a truncated URL: the username ended up
        # in the host position. A hostname merely lacking a dot is not enough
        # to conclude that, because internal hostnames on a platform network,
        # container names and localhost all legitimately have none, and a false
        # alarm sends someone to fix a password that was never wrong.
        report["issues"].append(
            f"The host and the user are both {host!r}. " + _password_hint())

    # A pooled connection routes by project, and the project reference travels
    # in the username. A bare "postgres" gives the pooler nothing to route on,
    # so it rejects the credentials and the failure reads as a wrong password.
    user = report.get("user") or ""
    if host and "pooler" in host and user and "." not in user:
        report["issues"].append(
            f"The user is {user!r}, but a pooled connection needs the project "
            "reference in the username, as postgres.<project-ref>. A bare "
            "'postgres' fails as a password error even when the password is "
            "correct. Copy the pooler string from the provider rather than "
            "editing the direct one.")
    return report


def _password_hint() -> str:
    encoded = ", ".join(f"{ch} as {code}" for ch, code
                        in list(RESERVED_IN_PASSWORD.items())[:4])
    return ("A password containing a reserved character ends the URL early and "
            "pushes the wrong text into the host position. Percent-encode it "
            f"({encoded}), or reset the database password to letters and "
            "digits only.")


def resolve_host(host: str) -> tuple[bool, str]:
    """Check whether a hostname resolves, so DNS is separated from auth."""
    import socket
    if not host:
        return False, "no host to resolve"
    try:
        socket.getaddrinfo(host, None)
        return True, "resolves"
    except socket.gaierror as exc:
        return False, str(exc)


def _is_connection_error(exc: Exception) -> bool:
    """True when the failure is the connection itself, not the statement."""
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        return False
    return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))


def _open_postgres(target: str):
    """Open a Postgres connection tuned for a managed, pooled database.

    prepare_threshold is disabled because a transaction-mode pooler, which is
    what several managed providers hand out by default, does not keep the
    session that a server-side prepared statement belongs to. Leaving psycopg
    to prepare statements automatically fails there with "prepared statement
    already exists". The queries here are not hot enough for the loss to
    matter.
    """
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        target,
        row_factory=dict_row,
        autocommit=False,
        prepare_threshold=None,
        connect_timeout=15,
    )


def connect(target: str) -> Store:
    """Open (or reuse) a per-thread connection.

    `target` is a DATABASE_URL for Postgres or a file path for SQLite.
    Flask serves requests on several threads, and neither driver's connections
    are safe to share across them.
    """
    cached = getattr(_local, "store", None)
    if cached is not None and getattr(_local, "target", None) == target:
        if cached.alive():
            return cached
        cached.close()
        _local.store = _local.target = None

    if _is_postgres_url(target):
        conn = _open_postgres(target)
        store = Store(conn, "postgres", target)
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
        store = Store(conn, "sqlite", target)

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


# ─── usage metering ────────────────────────────────────────────────────────

def record_usage(store: Store, row: dict[str, Any]) -> None:
    """Store one API call's cost. Never let metering break the feature."""
    try:
        store.execute(
            "INSERT INTO usage (ts, feature, model, user_email, input_tokens,"
            " output_tokens, cache_read, cache_write, web_searches, cost_usd)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), row.get("feature", ""), row.get("model", ""),
             row.get("user_email", ""), row.get("input_tokens", 0),
             row.get("output_tokens", 0), row.get("cache_read", 0),
             row.get("cache_write", 0), row.get("web_searches", 0),
             float(row.get("cost_usd", 0))))
        store.commit()
    except Exception:
        pass


def usage_summary(store: Store, days: int = 30) -> dict[str, Any]:
    """Spend broken down by feature, by day and by person."""
    def rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in store.execute(sql, params).fetchall()]

    totals = rows(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost,"
        " COALESCE(SUM(input_tokens),0) AS input_tokens,"
        " COALESCE(SUM(output_tokens),0) AS output_tokens,"
        " COALESCE(SUM(cache_read),0) AS cache_read,"
        " COALESCE(SUM(web_searches),0) AS web_searches FROM usage")
    by_feature = rows(
        "SELECT feature, COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost"
        " FROM usage GROUP BY feature ORDER BY cost DESC")
    by_day = rows(
        "SELECT substr(ts,1,10) AS day, COUNT(*) AS calls,"
        " COALESCE(SUM(cost_usd),0) AS cost FROM usage"
        " GROUP BY substr(ts,1,10) ORDER BY day DESC LIMIT ?", (days,))
    by_user = rows(
        "SELECT user_email, COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost"
        " FROM usage WHERE user_email <> '' GROUP BY user_email"
        " ORDER BY cost DESC LIMIT 25")
    recent = rows(
        "SELECT ts, feature, model, user_email, input_tokens, output_tokens,"
        " web_searches, cost_usd FROM usage ORDER BY ts DESC LIMIT 25")
    return {"totals": totals[0] if totals else {}, "by_feature": by_feature,
            "by_day": by_day, "by_user": by_user, "recent": recent}


def spend_today(store: Store) -> float:
    """Total cost recorded so far today, in dollars."""
    today = _now()[:10]
    row = store.execute(
        "SELECT COALESCE(SUM(cost_usd),0) AS spent FROM usage"
        " WHERE substr(ts,1,10) = ?", (today,)).fetchone()
    return float(row["spent"] if row else 0)
