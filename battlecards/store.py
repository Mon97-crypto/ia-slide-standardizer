"""Shared battlecard library, backed by Postgres.

Every card the builder generates is saved here, so the whole team browses one
library instead of passing decks around. Render provisions the database and hands
the app a `DATABASE_URL`.

The store is optional on purpose. With no `DATABASE_URL` the builder still
generates and downloads decks, `enabled()` returns False, and the gallery tells
the reader the library is not connected. That keeps local development and the
pre-database deployment working rather than crashing on import.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.parse

log = logging.getLogger(__name__)

_lock = threading.Lock()
_ready = False

# Render hands out postgres:// URLs; psycopg wants postgresql://.
_SCHEME = re.compile(r'^postgres://')

SCHEMA = """
CREATE TABLE IF NOT EXISTS battlecards (
    id            BIGSERIAL PRIMARY KEY,
    competitor    TEXT        NOT NULL,
    ia_product    TEXT        NOT NULL DEFAULT '',
    solution      TEXT        NOT NULL DEFAULT '',
    depth         TEXT        NOT NULL DEFAULT '',
    headline      TEXT        NOT NULL DEFAULT '',
    win_theme     TEXT        NOT NULL DEFAULT '',
    slide_count   INTEGER     NOT NULL DEFAULT 0,
    unverified    INTEGER     NOT NULL DEFAULT 0,
    curated       BOOLEAN     NOT NULL DEFAULT FALSE,
    author        TEXT        NOT NULL DEFAULT '',
    card          JSONB       NOT NULL,
    research      TEXT        NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    views         INTEGER     NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS battlecards_created_idx ON battlecards (created_at DESC);
CREATE INDEX IF NOT EXISTS battlecards_product_idx ON battlecards (ia_product);
CREATE INDEX IF NOT EXISTS battlecards_competitor_idx ON battlecards (lower(competitor));
"""


def database_url() -> str:
    url = os.environ.get('DATABASE_URL', '').strip()
    return _SCHEME.sub('postgresql://', url) if url else ''


def enabled() -> bool:
    """True when a database is configured and psycopg is importable."""
    if not database_url():
        return False
    try:
        import psycopg  # noqa: F401
        return True
    except ImportError:
        log.warning('DATABASE_URL is set but psycopg is not installed.')
        return False


# A serverless Postgres, Neon among them, parks its compute after a few minutes
# of quiet and wakes on the next connection. The wake takes a few seconds, and
# the first attempt is usually refused outright while it happens. One long
# timeout does not cover that: the refusal returns immediately, so the fix is to
# try again rather than to wait longer.
CONNECT_ATTEMPTS = 3
CONNECT_BACKOFF = (0.75, 2.5)

# Retrying is only right for a database that is coming up. These say it is not:
# the URL, the password or the name is wrong, and trying again just multiplies
# the wait before anybody finds out. A parked endpoint refuses fast, so failing
# fast here costs a wake nothing.
_FATAL = re.compile(
    r'password authentication failed'
    r'|role ".*" does not exist'
    r'|database ".*" does not exist'
    r'|could not translate host name'
    r'|name or service not known'
    r'|nodename nor servname'
    r'|no pg_hba.conf entry'
    r'|server does not support ssl'
    r'|channel binding'
    r'|certificate verify failed',
    re.IGNORECASE)


def connect_timeout() -> int:
    try:
        return max(3, min(int(os.environ.get('DB_CONNECT_TIMEOUT', 8)), 60))
    except ValueError:
        return 8


def _dsn() -> str:
    url = database_url()
    if not url:
        raise RuntimeError('DATABASE_URL is not set.')
    # Every managed provider requires TLS, and a URL that already names sslmode
    # is left alone so a provider's own setting wins. The host has to be parsed
    # rather than prefix matched: a real development URL carries credentials, so
    # postgresql://user:pw@127.0.0.1/db does not start with the host at all, and
    # requiring TLS against a local server that has none refuses the connection.
    if 'sslmode=' not in url and not _is_local(url):
        url += ('&' if '?' in url else '?') + 'sslmode=require'
    return url


_LOCAL_HOSTS = ('localhost', '127.0.0.1', '::1', 'host.docker.internal')


def _is_local(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).hostname or ''
    except ValueError:
        return False
    return host.lower() in _LOCAL_HOSTS


def _connect(attempts: int = None, timeout: int = None):
    """Open a connection, waiting out a wake but not a wrong password.

    `attempts` defaults to the full retry, which is what a write wants: a parked
    serverless endpoint refuses the first connection and is up a second later.
    A read or a probe passes 1, because a page load must not sit for half a
    minute to tell somebody the database is unreachable.
    """
    import psycopg
    url = _dsn()
    attempts = CONNECT_ATTEMPTS if attempts is None else max(1, attempts)
    timeout = connect_timeout() if timeout is None else timeout
    last = None
    for attempt in range(attempts):
        try:
            return psycopg.connect(url, connect_timeout=timeout)
        except psycopg.OperationalError as exc:
            last = exc
            first = (str(exc).strip().splitlines() or [''])[0]
            if _FATAL.search(first):
                log.warning('Database refused the connection for good: %s',
                            first[:160])
                raise
            if attempt == attempts - 1:
                break
            delay = CONNECT_BACKOFF[min(attempt, len(CONNECT_BACKOFF) - 1)]
            log.info('Database not up yet (%s). Waking it, retry in %.2fs.',
                     first[:120], delay)
            time.sleep(delay)
    raise last


def init(force: bool = False, attempts: int = None) -> bool:
    """Create the table if it is missing. Safe to call on every boot."""
    global _ready
    if not enabled():
        return False
    with _lock:
        if _ready and not force:
            return True
        try:
            with _connect(attempts=attempts) as conn:
                with conn.cursor() as cur:
                    cur.execute(SCHEMA)
                conn.commit()
            _ready = True
            log.info('Battlecard library is ready.')
            return True
        except Exception:
            log.exception('Could not prepare the battlecard library.')
            return False


def _row_to_summary(row) -> dict:
    return {
        'id': row[0], 'competitor': row[1], 'ia_product': row[2],
        'solution': row[3], 'depth': row[4], 'headline': row[5],
        'win_theme': row[6], 'slide_count': row[7], 'unverified': row[8],
        'curated': row[9], 'author': row[10],
        'created_at': row[11].isoformat() if row[11] else None,
        'views': row[12],
    }


_SUMMARY_COLUMNS = ('id, competitor, ia_product, solution, depth, headline, '
                    'win_theme, slide_count, unverified, curated, author, '
                    'created_at, views')


def save(card: dict, slide_count: int = 0, research: str = '',
         author: str = '', curated: bool = False) -> dict:
    """Store a card. Returns the saved summary, or an empty dict when disabled."""
    if not init():
        return {}
    meta = card.get('meta', {}) or {}
    unverified = sum(1 for row in card.get('comparison') or []
                     if row.get('competitor') == 'unknown')
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO battlecards (competitor, ia_product, solution, '
                    'depth, headline, win_theme, slide_count, unverified, '
                    'curated, author, card, research) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
                    'RETURNING ' + _SUMMARY_COLUMNS,
                    (meta.get('competitor', 'Unnamed'), meta.get('ia_product', ''),
                     meta.get('solution', ''), meta.get('depth', ''),
                     meta.get('headline', ''), meta.get('win_theme', ''),
                     int(slide_count or 0), unverified, bool(curated),
                     (author or '')[:120], json.dumps(card), (research or '')[:200000]))
                row = cur.fetchone()
            conn.commit()
        return _row_to_summary(row)
    except Exception:
        log.exception('Could not save the battlecard.')
        return {}


def listing(query: str = '', product: str = '', limit: int = 60) -> list:
    """Newest cards first, optionally filtered by text or product."""
    if not init():
        return []
    clauses, params = [], []
    if query:
        clauses.append('(competitor ILIKE %s OR headline ILIKE %s '
                       'OR win_theme ILIKE %s)')
        params.extend(['%%%s%%' % query] * 3)
    if product:
        clauses.append('ia_product = %s')
        params.append(product)
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    params.append(max(1, min(int(limit or 60), 200)))
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT ' + _SUMMARY_COLUMNS + ' FROM battlecards'
                            + where + ' ORDER BY created_at DESC LIMIT %s',
                            tuple(params))
                return [_row_to_summary(row) for row in cur.fetchall()]
    except Exception:
        log.exception('Could not list the battlecard library.')
        return []


def get(card_id: int, count_view: bool = True) -> dict:
    """Fetch one card in full, and count the read."""
    if not init():
        return {}
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                if count_view:
                    cur.execute('UPDATE battlecards SET views = views + 1 '
                                'WHERE id = %s', (int(card_id),))
                cur.execute('SELECT ' + _SUMMARY_COLUMNS + ', card, research '
                            'FROM battlecards WHERE id = %s', (int(card_id),))
                row = cur.fetchone()
            conn.commit()
        if not row:
            return {}
        entry = _row_to_summary(row)
        entry['card'] = row[13] if isinstance(row[13], dict) else json.loads(row[13])
        entry['research'] = row[14]
        return entry
    except Exception:
        log.exception('Could not read battlecard %s.', card_id)
        return {}


def delete(card_id: int) -> bool:
    if not init():
        return False
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM battlecards WHERE id = %s', (int(card_id),))
                removed = cur.rowcount
            conn.commit()
        return bool(removed)
    except Exception:
        log.exception('Could not delete battlecard %s.', card_id)
        return False


def describe() -> dict:
    """Say whether the database answers, and why not when it does not.

    `enabled()` only reports that a URL is set and psycopg imports, which is not
    the same as reachable. A wrong password looks identical to a working setup
    until the first write fails, so this actually connects.

    The credential never comes back out. Only the host, database and user, taken
    from the parsed URL, plus the error class and message, which name the cause
    without quoting the string that holds the password.
    """
    url = database_url()
    if not url:
        return {'configured': False, 'ok': False,
                'error': 'DATABASE_URL is not set.'}

    try:
        parts = urllib.parse.urlsplit(url)
        where = {'host': parts.hostname or '', 'port': parts.port or 5432,
                 'database': (parts.path or '/').lstrip('/'),
                 'user': parts.username or '',
                 'pooled': '-pooler' in (parts.hostname or '')}
    except ValueError as exc:
        return {'configured': True, 'ok': False,
                'error': 'DATABASE_URL could not be parsed: %s' % exc}

    try:
        import psycopg
    except ImportError:
        return dict(where, configured=True, ok=False,
                    error='psycopg is not installed in this deployment.')

    try:
        with _connect(attempts=1, timeout=6) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT version()')
                version = (cur.fetchone() or [''])[0]
    except Exception as exc:
        # The message can carry the whole DSN, so only the first line is kept and
        # anything password shaped is dropped.
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else ''
        first = re.sub(r'://[^@\s]+@', '://REDACTED@', first)[:300]
        return dict(where, configured=True, ok=False,
                    error='%s: %s' % (type(exc).__name__, first))

    return dict(where, configured=True, ok=True,
                server=version.split(' on ')[0][:80])


def stats() -> dict:
    """Headline numbers for the gallery, so it can say what is in the library."""
    if not init():
        return {'enabled': False, 'cards': 0, 'competitors': 0, 'products': 0}
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT COUNT(*), COUNT(DISTINCT lower(competitor)), '
                            'COUNT(DISTINCT ia_product) FROM battlecards')
                total, competitors, products = cur.fetchone()
        return {'enabled': True, 'cards': total or 0,
                'competitors': competitors or 0, 'products': products or 0}
    except Exception:
        log.exception('Could not read library stats.')
        return {'enabled': False, 'cards': 0, 'competitors': 0, 'products': 0}
