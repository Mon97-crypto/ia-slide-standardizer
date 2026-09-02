"""Staged connectivity check for the database.

"Connection failed" covers four unrelated faults with four unrelated fixes:
a value that was never set, a name that does not resolve, a port that refuses,
and credentials that are rejected. Reporting them as one message means guessing
between them. Each stage is tested separately here so the failure names itself.

Nothing in the output includes the password.
"""
from __future__ import annotations

import os
import socket
import time
from typing import Any

from .config import Config
from .db import describe_target, resolve_host

# Postgres and pooler errors mapped to the thing that actually needs changing.
ERROR_HINTS: list[tuple[str, str]] = [
    ("tenant or user not found",
     "The pooler did not recognise the user. On a pooled connection the "
     "username must carry the project reference, as postgres.<project-ref>. "
     "Copy it from the provider's pooler string."),
    ("password authentication failed",
     "The credentials were rejected. If the username has no project reference "
     "on a pooled host, that alone causes this even when the password is "
     "correct. Otherwise reset the database password and set it again."),
    ("does not exist",
     "The database name is wrong. On Supabase and Neon it is normally "
     "'postgres'. Check CIQ_DB_NAME."),
    ("no pg_hba.conf entry",
     "The server refused the connection's source or SSL mode. Add "
     "?sslmode=require to the URL, or check the provider's network rules."),
    ("ssl", "The server requires TLS. Add ?sslmode=require to the URL."),
    ("timeout",
     "The host accepted no connection in time. That usually means a firewall, "
     "or an IPv6 only direct connection the host cannot reach. Use the "
     "pooler endpoint instead."),
    ("connection refused",
     "Nothing is listening on that port. Check CIQ_DB_PORT, which is 5432 for "
     "a session pooler and 6543 for a transaction pooler."),
]


def _hint_for(message: str) -> str:
    lowered = message.lower()
    for needle, hint in ERROR_HINTS:
        if needle in lowered:
            return hint
    return ""


def _stage(name: str, ok: bool, detail: str = "", fix: str = "",
           ms: int | None = None) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix, "ms": ms}


def diagnose() -> dict[str, Any]:
    """Walk the connection one stage at a time and stop at the first failure."""
    stages: list[dict[str, Any]] = []

    # 1. Is anything configured, and where did it come from?
    url = Config.database_url()
    if not url:
        present = [k for k in ("DATABASE_URL", "CIQ_DB_HOST", "CIQ_DB_USER",
                               "CIQ_DB_PASSWORD", "CIQ_DB_NAME", "CIQ_DB_PORT")
                   if os.environ.get(k, "").strip()]
        stages.append(_stage(
            "Configuration", False,
            f"No database configured. Variables currently set: "
            f"{', '.join(present) if present else 'none of them'}.",
            "Set CIQ_DB_HOST, CIQ_DB_USER, CIQ_DB_PASSWORD, CIQ_DB_NAME and "
            "CIQ_DB_PORT, or a single DATABASE_URL."))
        return {"ok": False, "stages": stages}

    source = ("DATABASE_URL" if os.environ.get("DATABASE_URL", "").strip()
              else "CIQ_DB_* variables")
    stages.append(_stage("Configuration", True, f"Read from {source}."))

    # 2. Does the value parse into sensible parts?
    detail = describe_target(url)
    host, port = detail.get("host"), detail.get("port") or 5432
    if detail["issues"] or not host:
        stages.append(_stage(
            "Connection string", False,
            f"host={host!r} port={detail.get('port')!r} "
            f"user={detail.get('user')!r} database={detail.get('database')!r}",
            " ".join(detail["issues"]) or "No host could be read."))
        return {"ok": False, "stages": stages, "detail": detail}
    stages.append(_stage(
        "Connection string", True,
        f"host={host} port={port} user={detail.get('user')} "
        f"database={detail.get('database')}"))

    # 3. Does the hostname resolve?
    started = time.monotonic()
    resolves, dns = resolve_host(host)
    ms = int((time.monotonic() - started) * 1000)
    if not resolves:
        stages.append(_stage(
            "DNS", False, f"{host} did not resolve: {dns}",
            "The hostname is wrong, or a reserved character in the password "
            "truncated the URL and pushed other text into the host position.",
            ms))
        return {"ok": False, "stages": stages, "detail": detail}
    stages.append(_stage("DNS", True, f"{host} resolves.", ms=ms))

    # 4. Does the port accept a TCP connection?
    started = time.monotonic()
    try:
        with socket.create_connection((host, int(port)), timeout=10):
            pass
        ms = int((time.monotonic() - started) * 1000)
        stages.append(_stage("Network", True, f"Port {port} accepted a connection.", ms=ms))
    except Exception as exc:
        ms = int((time.monotonic() - started) * 1000)
        stages.append(_stage(
            "Network", False, f"Could not reach {host}:{port}. {exc}",
            _hint_for(str(exc)) or
            "Check the port, and prefer a pooler endpoint over a direct one.",
            ms))
        return {"ok": False, "stages": stages, "detail": detail}

    # 5. Do the credentials work?
    started = time.monotonic()
    try:
        import psycopg
        with psycopg.connect(url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        ms = int((time.monotonic() - started) * 1000)
        stages.append(_stage("Authentication", True, "Credentials accepted.", ms=ms))
    except Exception as exc:
        ms = int((time.monotonic() - started) * 1000)
        message = str(exc).strip().splitlines()[0]
        stages.append(_stage("Authentication", False, message,
                             _hint_for(message), ms))
        return {"ok": False, "stages": stages, "detail": detail}

    return {"ok": True, "stages": stages, "detail": detail}
