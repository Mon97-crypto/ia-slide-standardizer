"""Competitor knowledge: name normalisation, aliases, and IA product mapping.

Search quality lives or dies on this file. Analysts type "BY", "o9", "JDA" and
"relex" far more often than they type the registered company name, so every
lookup path resolves through the alias table before it touches the index.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Impact Analytics product portfolio, used to route a competitor to the IA
# product it actually threatens.
IA_PRODUCTS = [
    "ItemSmart", "PlanSmart", "AssortSmart", "PriceSmart", "MarkSmart",
    "PromoSmart", "InventorySmart", "SizeSmart", "StoreSmart",
    "AttributeSmart", "CortexEye",
]

# canonical name -> (aliases, IA products most exposed)
COMPETITORS: dict[str, dict] = {
    "o9 Solutions": {
        "aliases": ["o9", "o nine", "o9solutions"],
        "threatens": ["PlanSmart", "AssortSmart", "InventorySmart"],
    },
    "Blue Yonder": {
        # JDA is the legacy name. Analysts still write it, and older decks
        # still carry it, so it has to resolve to the current company.
        "aliases": ["blueyonder", "by", "jda", "jda software", "panasonic blue yonder"],
        "threatens": ["InventorySmart", "PlanSmart", "PriceSmart", "StoreSmart"],
    },
    "Relex Solutions": {
        "aliases": ["relex"],
        "threatens": ["InventorySmart", "PromoSmart", "StoreSmart"],
    },
    "SAP": {
        "aliases": ["sap ibp", "sap retail", "sap cargill"],
        "threatens": ["PlanSmart", "InventorySmart"],
    },
    "Oracle Retail": {
        "aliases": ["oracle", "oracle rpas", "oracle retail science"],
        "threatens": ["PlanSmart", "PriceSmart", "AssortSmart"],
    },
    "Anaplan": {
        "aliases": ["anaplan"],
        "threatens": ["PlanSmart"],
    },
    "Kinaxis": {
        "aliases": ["kinaxis", "rapidresponse", "rapid response"],
        "threatens": ["InventorySmart", "PlanSmart"],
    },
    "Manhattan Associates": {
        "aliases": ["manhattan", "manh"],
        "threatens": ["InventorySmart", "StoreSmart"],
    },
    "ToolsGroup": {
        "aliases": ["toolsgroup", "tools group", "so99", "justenough"],
        "threatens": ["InventorySmart", "PlanSmart"],
    },
    "Logility": {
        "aliases": ["logility", "american software"],
        "threatens": ["PlanSmart", "InventorySmart"],
    },
    "Nextail": {
        "aliases": ["nextail labs"],
        "threatens": ["AssortSmart", "SizeSmart", "StoreSmart"],
    },
    "Increff": {
        "aliases": ["increff"],
        "threatens": ["AssortSmart", "SizeSmart", "InventorySmart"],
    },
    "First Insight": {
        "aliases": ["firstinsight"],
        "threatens": ["ItemSmart", "AssortSmart"],
    },
    "EDITED": {
        "aliases": ["edited market intelligence"],
        "threatens": ["CortexEye", "PriceSmart"],
    },
    "Revionics": {
        "aliases": ["revionics", "aptos revionics"],
        "threatens": ["PriceSmart", "MarkSmart", "PromoSmart"],
    },
    "Symphony RetailAI": {
        "aliases": ["symphony retail", "symphonyai retail", "symphonyai"],
        "threatens": ["PromoSmart", "PriceSmart", "AssortSmart"],
    },
    "Aera Technology": {
        "aliases": ["aera"],
        "threatens": ["PlanSmart", "InventorySmart"],
    },
    "Antuit.ai": {
        "aliases": ["antuit", "antuit ai", "zebra antuit"],
        "threatens": ["PlanSmart", "InventorySmart"],
    },
    "Retalon": {
        "aliases": ["retalon"],
        "threatens": ["PlanSmart", "AssortSmart", "InventorySmart"],
    },
    "Syrup Tech": {
        "aliases": ["syrup"],
        "threatens": ["AssortSmart", "InventorySmart"],
    },
    "e2open": {
        "aliases": ["e2 open"],
        "threatens": ["InventorySmart"],
    },
    "Board International": {
        "aliases": ["board", "board intl"],
        "threatens": ["PlanSmart"],
    },
}

# The four Impact Analytics solution areas and their brand colours. Used as a
# small indicator on a result, never as a wash over the whole card: the primary
# palette leads, and a solution colour appears only where it means something.
SOLUTIONS: dict[str, dict[str, str]] = {
    "merchandising": {"label": "Merchandising", "color": "#BEA8EF"},
    "inventory": {"label": "Inventory and replenishment", "color": "#E3F576"},
    "pricing": {"label": "Pricing and promotions", "color": "#3DD499"},
    "data": {"label": "Data and intelligence", "color": "#B3C9F7"},
}

PRODUCT_SOLUTION: dict[str, str] = {
    "ItemSmart": "merchandising", "SizeSmart": "merchandising",
    "AssortSmart": "merchandising", "AttributeSmart": "merchandising",
    "InventorySmart": "inventory", "ForecastSmart": "inventory",
    "StoreSmart": "inventory",
    "PlanSmart": "pricing", "PromoSmart": "pricing",
    "PriceSmart": "pricing", "MarkSmart": "pricing",
    "MondaySmart": "data", "CortexEye": "data",
}


def solution_for(competitor: str) -> dict[str, str]:
    """The solution area a competitor most threatens, with its brand colour."""
    for product in threatened_products(competitor):
        key = PRODUCT_SOLUTION.get(product)
        if key:
            return {"key": key, **SOLUTIONS[key]}
    return {"key": "data", **SOLUTIONS["data"]}


_WORD_RE = re.compile(r"[a-z0-9]+")


def normalise(text: str) -> str:
    """Lowercase, strip accents, collapse punctuation to single spaces."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(_WORD_RE.findall(text.lower()))


def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, meta in COMPETITORS.items():
        index[normalise(canonical)] = canonical
        for alias in meta["aliases"]:
            index[normalise(alias)] = canonical
    return index


ALIAS_INDEX = _alias_index()


def canonical_name(raw: str) -> str:
    """Resolve any spelling of a competitor to its canonical name.

    Unknown companies pass through with their original text preserved, so the
    library is never limited to the vendors hardcoded above.
    """
    key = normalise(raw)
    if not key:
        return ""
    return ALIAS_INDEX.get(key, raw.strip())


def competitor_key(raw: str) -> str:
    """Stable grouping key. Every alias of one company collapses to one key."""
    return normalise(canonical_name(raw))


def resolve(raw: str, cutoff: float = 0.82) -> tuple[str, float]:
    """Resolve a possibly misspelled competitor name.

    Returns the canonical name and a confidence score. Exact and alias hits
    score 1.0. Anything below the cutoff is rejected rather than guessed at,
    because a wrong competitor is worse than no competitor.
    """
    key = normalise(raw)
    if not key:
        return "", 0.0
    if key in ALIAS_INDEX:
        return ALIAS_INDEX[key], 1.0

    best, best_score = "", 0.0
    for alias, canonical in ALIAS_INDEX.items():
        # Substring containment is a strong signal for short tokens like "o9".
        if len(key) >= 3 and (key in alias or alias in key):
            score = 0.9
        else:
            score = SequenceMatcher(None, key, alias).ratio()
        if score > best_score:
            best, best_score = canonical, score
    if best_score >= cutoff:
        return best, round(best_score, 3)
    return "", round(best_score, 3)


def threatened_products(competitor: str) -> list[str]:
    meta = COMPETITORS.get(canonical_name(competitor))
    return list(meta["threatens"]) if meta else []


def known_names() -> list[str]:
    return sorted(COMPETITORS)
