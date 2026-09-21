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


def _connect():
    import psycopg
    url = database_url()
    if not url:
        raise RuntimeError('DATABASE_URL is not set.')
    # Render's managed Postgres requires TLS. libpq negotiates it by default, and
    # a URL that already names sslmode is left alone.
    if 'sslmode=' not in url and not url.startswith('postgresql://localhost'):
        url += ('&' if '?' in url else '?') + 'sslmode=prefer'
    return psycopg.connect(url, connect_timeout=10)


def init(force: bool = False) -> bool:
    """Create the table if it is missing. Safe to call on every boot."""
    global _ready
    if not enabled():
        return False
    with _lock:
        if _ready and not force:
            return True
        try:
            with _connect() as conn:
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
