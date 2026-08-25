"""Glue between the web layer and the battlecard engine."""

from __future__ import annotations

import json
import os
import re
import uuid

from .brand import PRODUCT_SOLUTIONS, SOLUTION_LABELS
from .builder import build_presentation
from .compat import audit
from .library import COMPETITOR_PRESETS, PRODUCT_CATALOG, scaffold
from .schema import SECTION_LABELS, SECTION_ORDER, normalize, validate

_SAFE_NAME = re.compile(r'[^A-Za-z0-9]+')


def presets() -> dict:
    """Everything the builder UI needs to render its pickers."""
    return {
        'solutions': [{'key': key, 'label': label} for key, label in SOLUTION_LABELS.items()],
        'products': [dict(entry, solution_label=SOLUTION_LABELS[entry['solution']])
                     for entry in PRODUCT_CATALOG],
        'competitors': COMPETITOR_PRESETS,
        'sections': [{'key': key, 'label': SECTION_LABELS[key]} for key in SECTION_ORDER],
        'product_solutions': PRODUCT_SOLUTIONS,
    }


def starter(competitor: str = '', product: str = '', solution: str = '') -> dict:
    return scaffold(competitor, product, solution)


def review(payload: dict) -> dict:
    card = normalize(payload)
    result = validate(card)
    result['card'] = card
    return result


def build(payload: dict, output_dir: str) -> dict:
    """Normalise, validate and write the deck. Raises ValueError on bad input."""
    card = normalize(payload)
    checks = validate(card)
    if checks['errors']:
        raise ValueError('; '.join(checks['errors']))

    presentation = build_presentation(card)
    os.makedirs(output_dir, exist_ok=True)
    filename = _filename(card)
    path = os.path.join(output_dir, filename)
    presentation.save(path)

    return {
        'filename': filename,
        'path': path,
        'slide_count': len(presentation.slides._sldIdLst),
        'warnings': checks['warnings'],
        'compatibility': audit(path),
        'card': card,
    }


def export_json(payload: dict) -> str:
    return json.dumps(normalize(payload), indent=2, sort_keys=True)


def _filename(card: dict) -> str:
    competitor = _SAFE_NAME.sub('_', card['meta']['competitor']).strip('_') or 'Competitor'
    product = _SAFE_NAME.sub('_', card['meta'].get('ia_product', '')).strip('_')
    parts = ['IA_Battlecard', competitor]
    if product:
        parts.append(product)
    parts.append(uuid.uuid4().hex[:8])
    return '_'.join(parts) + '.pptx'
