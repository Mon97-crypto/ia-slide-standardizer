"""Battlecard data model, normalisation and brand copy checks.

The builder accepts loose JSON from the web form or an API client and turns it
into a strict structure the slide builders can rely on. The same module enforces
the writing rules from the IA brand guide, so no dash slips into a deck.
"""

from __future__ import annotations

import re
from datetime import date

MAX_TEXT = 1200
MAX_ROWS = 60

RATING_VALUES = ('strong', 'partial', 'none', 'unknown')
RATING_LABELS = {
    'strong': 'Strong',
    'partial': 'Partial',
    'none': 'Gap',
    'unknown': 'Unclear',
}

SECTION_ORDER = [
    'cover',
    'how_to_use',
    'snapshot',
    'positioning',
    'strengths_weaknesses',
    'why_we_win',
    'comparison',
    'objections',
    'landmines',
    'discovery',
    'proof_points',
    'talk_track',
    'dos_donts',
    'pricing',
    'next_steps',
    'one_pager',
]

SECTION_LABELS = {
    'cover': 'Cover',
    'how_to_use': 'How to use this card',
    'snapshot': 'Competitor snapshot',
    'positioning': 'Positioning face off',
    'strengths_weaknesses': 'Where they win, where they fall short',
    'why_we_win': 'Why we win',
    'comparison': 'Head to head matrix',
    'objections': 'Objection handling',
    'landmines': 'Landmines to set',
    'discovery': 'Discovery questions',
    'proof_points': 'Proof points',
    'talk_track': 'Talk track',
    'dos_donts': 'Do and do not',
    'pricing': 'Pricing and packaging',
    'next_steps': 'Next steps and resources',
    'one_pager': 'One page summary',
}

DEFAULT_SECTIONS = list(SECTION_ORDER)


# ─── Copy rules from the brand guide ────────────────────────────────────────────

_DASH_PATTERN = re.compile(r'\s*[—–]\s*')
_TERMINAL_PREPOSITIONS = {
    'about', 'above', 'across', 'after', 'against', 'along', 'among', 'around',
    'at', 'before', 'behind', 'below', 'beneath', 'beside', 'between', 'beyond',
    'by', 'down', 'during', 'for', 'from', 'in', 'inside', 'into', 'near', 'of',
    'off', 'on', 'onto', 'out', 'outside', 'over', 'through', 'to', 'toward',
    'under', 'up', 'upon', 'with', 'within', 'without',
}
_STAT_YEAR = re.compile(r'\b(19\d{2}|20[0-2]\d)\b')


def sanitize_text(value) -> str:
    """Strip dashes the brand guide bans and normalise whitespace."""
    if value is None:
        return ''
    text = str(value).replace('\r\n', '\n').replace('\r', '\n')
    text = _DASH_PATTERN.sub(', ', text)
    text = text.replace('—', ',').replace('–', ',')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r',\s*,', ',', text)
    return text.strip()[:MAX_TEXT]


def lint_copy(value: str, where: str) -> list:
    """Flag brand voice problems without changing the text."""
    issues = []
    if not value:
        return issues
    if '—' in value or '–' in value:
        issues.append({'where': where, 'rule': 'dashes',
                       'message': 'Replace the dash with a comma or a period.'})
    for sentence in re.split(r'(?<=[.!?])\s+', value):
        words = re.findall(r"[A-Za-z']+", sentence)
        if words and words[-1].lower() in _TERMINAL_PREPOSITIONS:
            issues.append({'where': where, 'rule': 'terminal_preposition',
                           'message': 'Rewrite so the sentence does not end with "%s".' % words[-1]})
            break
    if re.search(r'\b(FAQ|FAQs)\b', value):
        issues.append({'where': where, 'rule': 'faq_heading',
                       'message': 'Use "Frequently Asked Questions" instead of "FAQ".'})
    if re.search(r'\d{1,3}(\.\d+)?\s?%|\$\s?\d', value):
        years = _STAT_YEAR.findall(value)
        if years and all(int(year) < 2025 for year in years):
            issues.append({'where': where, 'rule': 'stat_recency',
                           'message': 'Cite a statistic from 2025 or later.'})
    return issues


# ─── Coercion helpers ───────────────────────────────────────────────────────────

def _clean_str(value, sanitize=True) -> str:
    return sanitize_text(value) if sanitize else (str(value).strip() if value else '')


def _clean_list(value, sanitize=True, limit=MAX_ROWS) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        items = [line for line in value.split('\n')]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]
    out = []
    for item in items:
        text = _clean_str(item, sanitize)
        if text:
            out.append(text)
    return out[:limit]


def _clean_records(value, fields, sanitize=True, limit=MAX_ROWS) -> list:
    if not isinstance(value, (list, tuple)):
        return []
    rows = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            continue
        row = {}
        for field, kind in fields.items():
            raw = item.get(field)
            if kind == 'list':
                row[field] = _clean_list(raw, sanitize)
            elif kind == 'rating':
                row[field] = _clean_rating(raw)
            else:
                row[field] = _clean_str(raw, sanitize)
        if any(row.get(field) for field in fields):
            rows.append(row)
    return rows


def _clean_rating(value) -> str:
    text = str(value or '').strip().lower()
    aliases = {
        'yes': 'strong', 'full': 'strong', 'native': 'strong', 'strong': 'strong',
        'partial': 'partial', 'limited': 'partial', 'some': 'partial',
        'no': 'none', 'gap': 'none', 'none': 'none', 'missing': 'none',
    }
    return aliases.get(text, 'unknown' if text not in RATING_VALUES else text)


def normalize(payload: dict) -> dict:
    """Turn a loose payload into the strict battlecard structure."""
    payload = payload if isinstance(payload, dict) else {}
    sanitize = bool(payload.get('sanitize_copy', True))

    meta_in = payload.get('meta') if isinstance(payload.get('meta'), dict) else payload
    competitor = _clean_str(meta_in.get('competitor'), sanitize) or 'Competitor'
    product = _clean_str(meta_in.get('ia_product'), sanitize)

    meta = {
        'competitor': competitor,
        'competitor_category': _clean_str(meta_in.get('competitor_category'), sanitize),
        'ia_product': product,
        'solution': _clean_str(meta_in.get('solution'), False),
        'owner': _clean_str(meta_in.get('owner'), sanitize),
        'audience': _clean_str(meta_in.get('audience'), sanitize) or 'Sales and solution consulting',
        'date': _clean_str(meta_in.get('date'), False) or date.today().strftime('%B %Y'),
        'version': _clean_str(meta_in.get('version'), False) or 'v1.0',
        'confidentiality': _clean_str(meta_in.get('confidentiality'), sanitize) or 'Internal use only',
        'headline': _clean_str(meta_in.get('headline'), sanitize),
        'win_theme': _clean_str(meta_in.get('win_theme'), sanitize),
    }

    snapshot = payload.get('snapshot') if isinstance(payload.get('snapshot'), dict) else {}
    card = {
        'meta': meta,
        'snapshot': {
            'headquarters': _clean_str(snapshot.get('headquarters'), sanitize),
            'founded': _clean_str(snapshot.get('founded'), sanitize),
            'employees': _clean_str(snapshot.get('employees'), sanitize),
            'ownership': _clean_str(snapshot.get('ownership'), sanitize),
            'funding': _clean_str(snapshot.get('funding'), sanitize),
            'target_segment': _clean_str(snapshot.get('target_segment'), sanitize),
            'go_to_market': _clean_str(snapshot.get('go_to_market'), sanitize),
            'deployment': _clean_str(snapshot.get('deployment'), sanitize),
            'notable_customers': _clean_str(snapshot.get('notable_customers'), sanitize),
            'recent_moves': _clean_list(snapshot.get('recent_moves'), sanitize),
        },
        'positioning': {
            'their_claim': _clean_str((payload.get('positioning') or {}).get('their_claim'), sanitize),
            'our_claim': _clean_str((payload.get('positioning') or {}).get('our_claim'), sanitize),
            'wedge': _clean_str((payload.get('positioning') or {}).get('wedge'), sanitize),
        } if isinstance(payload.get('positioning'), dict) else {
            'their_claim': '', 'our_claim': '', 'wedge': ''},
        'their_strengths': _clean_list(payload.get('their_strengths'), sanitize),
        'their_weaknesses': _clean_list(payload.get('their_weaknesses'), sanitize),
        'our_advantages': _clean_records(
            payload.get('our_advantages'),
            {'title': 'str', 'detail': 'str', 'proof': 'str'}, sanitize),
        'comparison': _clean_records(
            payload.get('comparison'),
            {'capability': 'str', 'ia': 'rating', 'competitor': 'rating', 'note': 'str'},
            sanitize),
        'objections': _clean_records(
            payload.get('objections'),
            {'objection': 'str', 'response': 'str', 'proof': 'str'}, sanitize),
        'landmines': _clean_records(
            payload.get('landmines'),
            {'question': 'str', 'why': 'str', 'listen_for': 'str'}, sanitize),
        'discovery': _clean_records(
            payload.get('discovery'),
            {'theme': 'str', 'questions': 'list'}, sanitize),
        'proof_points': _clean_records(
            payload.get('proof_points'),
            {'stat': 'str', 'label': 'str', 'detail': 'str', 'source': 'str'}, sanitize),
        'talk_track': {
            'positioning': _clean_str((payload.get('talk_track') or {}).get('positioning'), sanitize),
            'elevator': _clean_str((payload.get('talk_track') or {}).get('elevator'), sanitize),
            'discovery_open': _clean_str((payload.get('talk_track') or {}).get('discovery_open'), sanitize),
            'trap': _clean_str((payload.get('talk_track') or {}).get('trap'), sanitize),
        } if isinstance(payload.get('talk_track'), dict) else {
            'positioning': '', 'elevator': '', 'discovery_open': '', 'trap': ''},
        'dos': _clean_list(payload.get('dos'), sanitize),
        'donts': _clean_list(payload.get('donts'), sanitize),
        'pricing': {
            'ia_model': _clean_str((payload.get('pricing') or {}).get('ia_model'), sanitize),
            'competitor_model': _clean_str((payload.get('pricing') or {}).get('competitor_model'), sanitize),
            'notes': _clean_list((payload.get('pricing') or {}).get('notes'), sanitize),
        } if isinstance(payload.get('pricing'), dict) else {
            'ia_model': '', 'competitor_model': '', 'notes': []},
        'next_steps': _clean_list(payload.get('next_steps'), sanitize),
        'resources': _clean_records(
            payload.get('resources'), {'label': 'str', 'url': 'str'}, sanitize),
        'how_to_use': _clean_list(payload.get('how_to_use'), sanitize),
        'options': {
            'sections': _valid_sections(payload.get('sections')),
            'serif_headings': bool((payload.get('options') or {}).get('serif_headings', False)),
            'include_notes': bool((payload.get('options') or {}).get('include_notes', True)),
            'sanitize_copy': sanitize,
        },
    }

    for row in card['resources']:
        row['url'] = _safe_url(row.get('url'))

    for row in card['proof_points']:
        row['source'] = _safe_url(row.get('source')) if _looks_like_url(row.get('source')) else row.get('source', '')

    return card


def _looks_like_url(value: str) -> bool:
    return bool(value) and re.match(r'^(https?://|www\.)', value.strip(), re.I) is not None


def _safe_url(value: str) -> str:
    """Keep only http and https links, so no javascript: URL reaches a slide."""
    text = (value or '').strip()
    if not text:
        return ''
    if text.lower().startswith('www.'):
        text = 'https://' + text
    if not re.match(r'^https?://', text, re.I):
        return ''
    return text[:500]


def _valid_sections(value) -> list:
    if not value:
        return list(DEFAULT_SECTIONS)
    if isinstance(value, str):
        value = [part.strip() for part in value.split(',')]
    chosen = [name for name in SECTION_ORDER if name in set(value)]
    if 'cover' not in chosen:
        chosen.insert(0, 'cover')
    return chosen


def validate(card: dict) -> dict:
    """Return blocking errors and non blocking brand warnings."""
    errors = []
    warnings = []

    if not card['meta']['competitor'] or card['meta']['competitor'] == 'Competitor':
        errors.append('Name the competitor this card covers.')

    filled = sum(1 for key in ('their_strengths', 'their_weaknesses', 'our_advantages',
                               'comparison', 'objections', 'proof_points')
                 if card.get(key))
    if filled == 0:
        errors.append('Fill at least one battlecard section before you build the deck.')

    if not card['proof_points']:
        warnings.append({'where': 'proof_points', 'rule': 'evidence',
                         'message': 'Add proof points. The brand voice leads with data.'})
    for row in card['proof_points']:
        if not row.get('source'):
            warnings.append({'where': 'proof_points', 'rule': 'source_link',
                             'message': 'Add a source link for "%s".' % (row.get('stat') or row.get('label'))})

    for key, label in (('their_strengths', 'their_strengths'), ('their_weaknesses', 'their_weaknesses'),
                       ('dos', 'dos'), ('donts', 'donts'), ('next_steps', 'next_steps')):
        for text in card.get(key, []):
            warnings.extend(lint_copy(text, label))

    for row in card.get('objections', []):
        warnings.extend(lint_copy(row.get('response', ''), 'objections'))
    for row in card.get('our_advantages', []):
        warnings.extend(lint_copy(row.get('detail', ''), 'our_advantages'))
    for value in card.get('talk_track', {}).values():
        warnings.extend(lint_copy(value, 'talk_track'))

    seen = set()
    unique = []
    for warning in warnings:
        key = (warning['where'], warning['rule'], warning['message'])
        if key not in seen:
            seen.add(key)
            unique.append(warning)

    return {'errors': errors, 'warnings': unique[:40]}
