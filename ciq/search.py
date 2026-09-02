"""Query understanding and ranking.

The search box is the product. An analyst types "o9 battlecard" and expects the
o9 battlecard, so a query is parsed into its parts before anything is matched:

    "o9 battlecard"      -> competitor=o9 Solutions, category=battlecard
    "jda pricing notes"  -> competitor=Blue Yonder, category=information,
                            terms=["pricing"]
    "bleu yonder"        -> competitor=Blue Yonder (fuzzy, typo tolerated)

Structured parts become filters. Whatever is left becomes a BM25 full-text
query across the competitor, title, note and document body, with the body
weighted lowest so a passing mention never outranks a real title match.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .competitors import ALIAS_INDEX, normalise, resolve
from .db import Store, entries_where, passage_scores, text_scores

# Phrases an analyst actually types, mapped to the stored category.
CATEGORY_LEXICON: dict[str, tuple[str, ...]] = {
    "battlecard": ("battlecard", "battlecards", "battle card", "battle cards"),
    "client_list": (
        "client list", "client lists", "clients", "client references",
        "references", "logos", "customer list", "customers", "wins",
    ),
    "master_sheet": (
        "master sheet", "master sheets", "mastersheet", "master", "consolidated",
        "matrix", "comparison sheet",
    ),
    "information": (
        "research", "information", "notes", "analysis", "intel",
        "intelligence", "overview", "profile", "deep dive", "background",
    ),
}

# Longest phrases first so "client list" wins over "clients".
_CATEGORY_PHRASES: list[tuple[str, str]] = sorted(
    ((normalise(phrase), category)
     for category, phrases in CATEGORY_LEXICON.items()
     for phrase in phrases),
    key=lambda pair: -len(pair[0]),
)

_MAX_ALIAS_WORDS = max(len(alias.split()) for alias in ALIAS_INDEX)

# Weights. Ordering matters more than the absolute numbers.
W_COMPETITOR = 3.0
W_CATEGORY = 2.0
W_TEXT = 4.0
W_RECENCY = 0.3

# Dropped from residual terms. They carry no signal and only dilute BM25.
STOPWORDS = frozenset("""
a an the of for from on in to with and or vs versus about our their
me my we us you your please show find get any all latest new
""".split())


@dataclass
class QueryIntent:
    raw: str = ""
    competitor: str = ""
    competitor_confidence: float = 0.0
    category: str = ""
    terms: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.competitor or self.category or self.terms)

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "competitor": self.competitor,
            "competitor_confidence": self.competitor_confidence,
            "category": self.category,
            "terms": self.terms,
        }


def _strip_phrase(tokens: list[str], phrase_tokens: list[str]) -> list[str] | None:
    """Remove the first contiguous run of phrase_tokens. None if absent."""
    span = len(phrase_tokens)
    for start in range(len(tokens) - span + 1):
        if tokens[start:start + span] == phrase_tokens:
            return tokens[:start] + tokens[start + span:]
    return None


def parse_query(raw: str) -> QueryIntent:
    """Split a free-text query into competitor, category and residual terms."""
    intent = QueryIntent(raw=(raw or "").strip())
    tokens = normalise(raw).split()
    if not tokens:
        return intent

    # 1. Category phrases, longest first.
    for phrase, category in _CATEGORY_PHRASES:
        stripped = _strip_phrase(tokens, phrase.split())
        if stripped is not None:
            intent.category = category
            tokens = stripped
            break

    # 2. Competitor, preferring the longest alias that matches exactly.
    for span in range(min(_MAX_ALIAS_WORDS, len(tokens)), 0, -1):
        matched = False
        for start in range(len(tokens) - span + 1):
            candidate = " ".join(tokens[start:start + span])
            if candidate in ALIAS_INDEX:
                intent.competitor = ALIAS_INDEX[candidate]
                intent.competitor_confidence = 1.0
                tokens = tokens[:start] + tokens[start + span:]
                matched = True
                break
        if matched:
            break

    # 3. No exact hit, so allow one fuzzy attempt per remaining token. This is
    #    what rescues "bleu yonder" and "relexx".
    if not intent.competitor:
        for span in (2, 1):
            if intent.competitor:
                break
            for start in range(len(tokens) - span + 1):
                candidate = " ".join(tokens[start:start + span])
                if len(candidate) < 3:
                    continue
                name, score = resolve(candidate)
                if name:
                    intent.competitor = name
                    intent.competitor_confidence = score
                    tokens = tokens[:start] + tokens[start + span:]
                    break

    intent.terms = [t for t in tokens if t not in STOPWORDS]
    return intent


def _recency_score(created_at: str) -> float:
    """Newer intel edges out older intel when everything else ties."""
    try:
        stamp = datetime.fromisoformat(created_at)
    except (TypeError, ValueError):
        return 0.0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - stamp).days
    if age_days <= 7:
        return 1.0
    if age_days >= 365:
        return 0.0
    return max(0.0, 1.0 - (age_days / 365.0))


def search(store: Store, query: str = "", category: str = "",
           limit: int = 60) -> dict[str, Any]:
    """Rank library entries against a query.

    `category` is the UI filter chip and always wins over a category inferred
    from the query text, because an explicit click beats a guess.
    """
    intent = parse_query(query)
    effective_category = category if category and category != "all" else intent.category

    candidates = {
        e["id"]: e for e in entries_where(
            store,
            category=effective_category,
            competitor_key_value=normalise(intent.competitor) if intent.competitor else "",
        )
    }

    scores = text_scores(store, intent.terms)

    if scores and not intent.competitor and not effective_category:
        # Free-text-only query: the matched set is the candidate set.
        candidates = {i: e for i, e in candidates.items() if i in scores}

    top_text = max(scores.values(), default=0.0) or 1.0

    results = []
    for entry_id, entry in candidates.items():
        score = 0.0
        why: list[str] = []

        if intent.competitor:
            score += W_COMPETITOR * intent.competitor_confidence
            label = f"competitor {intent.competitor}"
            if intent.competitor_confidence < 1.0:
                label += " (closest match)"
            why.append(label)

        if effective_category:
            score += W_CATEGORY
            why.append(f"type {effective_category.replace('_', ' ')}")

        relevance = scores.get(entry_id, 0.0)
        if relevance:
            score += W_TEXT * (relevance / top_text)
            # Name only the terms that genuinely appear, so the explanation
            # under a result can be trusted rather than merely echoing the box.
            haystack = normalise(" ".join((
                entry.get("title", ""), entry.get("note", ""),
                entry.get("competitor", ""), entry.get("content", ""))))
            hits = [t for t in intent.terms if t in haystack]
            why.append("text match on " + ", ".join(hits or intent.terms))
        elif intent.terms and not intent.competitor and not effective_category:
            continue

        score += W_RECENCY * _recency_score(entry.get("created_at", ""))

        entry = dict(entry)
        entry["score"] = round(score, 4)
        entry["why"] = why
        results.append(entry)

    if intent.is_empty:
        results.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    else:
        results.sort(key=lambda e: (-e["score"], e.get("created_at", "")))

    return {
        "intent": intent.as_dict(),
        "effective_category": effective_category,
        "total": len(results),
        "results": results[:limit],
    }


def retrieve_passages(store: Store, question: str, entry_id: str = "",
                      competitor: str = "", limit: int = 8) -> list[dict[str, Any]]:
    """Fetch the passages most likely to answer a question.

    This is what replaces blindly sending the first few thousand characters of
    a document to the model. A long file stays answerable because the relevant
    passage is retrieved wherever it sits in the file.
    """
    terms = [t for t in normalise(question).split()
             if len(t) > 2 and t not in STOPWORDS]
    return passage_scores(
        store, terms, entry_id=entry_id,
        competitor_key_value=normalise(competitor) if competitor else "",
        limit=limit)


def gather_passages(store: Store, themes: dict[str, str], competitor: str,
                    per_theme: int = 4, cap: int = 28) -> list[dict[str, Any]]:
    """Sweep the library once per theme and merge the results.

    A single query only ever surfaces one theme. A battlecard needs pricing,
    implementation, customers and product gaps at the same time, so each theme
    is retrieved separately and the union is merged.

    A passage is attributed to the theme that scores it highest, not to
    whichever theme happened to run first. Themes overlap heavily on a small
    corpus, so first-come attribution would let a broad theme monopolise
    passages a narrower one describes better. The merge then takes the best
    few per theme before filling the remainder by score, which keeps breadth
    without sacrificing the strongest matches.
    """
    key = normalise(competitor) if competitor else ""
    best: dict[str, dict[str, Any]] = {}

    for theme, query in themes.items():
        terms = [t for t in normalise(query).split()
                 if len(t) > 2 and t not in STOPWORDS]
        for passage in passage_scores(store, terms, competitor_key_value=key,
                                      limit=per_theme * 5):
            fingerprint = passage["text"][:160]
            previous = best.get(fingerprint)
            if previous is None or passage["score"] > previous["score"]:
                claimed = dict(passage)
                claimed["theme"] = theme
                best[fingerprint] = claimed

    by_theme: dict[str, list[dict[str, Any]]] = {}
    for passage in best.values():
        by_theme.setdefault(passage["theme"], []).append(passage)

    merged: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    for theme in themes:
        ranked = sorted(by_theme.get(theme, []), key=lambda x: -x["score"])
        merged.extend(ranked[:per_theme])
        overflow.extend(ranked[per_theme:])

    merged.sort(key=lambda x: -x["score"])
    overflow.sort(key=lambda x: -x["score"])
    merged.extend(overflow[:max(0, cap - len(merged))])

    # A competitor with only one short document should still produce a card,
    # so fall back to whatever is on file when the themed sweep finds nothing.
    if not merged and key:
        for entry in entries_where(store, competitor_key_value=key):
            for text in (entry.get("content") or "").split("\n\n")[:6]:
                if text.strip():
                    merged.append({
                        "entry_id": entry["id"], "title": entry["title"],
                        "competitor": entry["competitor"],
                        "category": entry["category"], "text": text.strip(),
                        "score": 0.0, "theme": "fallback",
                    })

    return merged[:cap]
