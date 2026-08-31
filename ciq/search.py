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

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .competitors import ALIAS_INDEX, normalise, resolve
from .db import row_to_dict

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


def _fts_query(terms: list[str]) -> str:
    """Build a safe FTS5 MATCH expression with prefix matching on each term."""
    cleaned = []
    for term in terms:
        safe = re.sub(r'[^0-9a-z]+', "", term.lower())
        if safe:
            cleaned.append(f'"{safe}"*')
    return " OR ".join(cleaned)


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


def search(conn: sqlite3.Connection, query: str = "", category: str = "",
           limit: int = 60) -> dict[str, Any]:
    """Rank library entries against a query.

    `category` is the UI filter chip and always wins over a category inferred
    from the query text, because an explicit click beats a guess.
    """
    intent = parse_query(query)
    effective_category = category if category and category != "all" else intent.category

    clauses: list[str] = []
    params: list[Any] = []
    if effective_category:
        clauses.append("e.category = ?")
        params.append(effective_category)
    if intent.competitor:
        clauses.append("e.competitor_key = ?")
        params.append(normalise(intent.competitor))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    rows = conn.execute(
        f"SELECT e.* FROM entries e {where}", params).fetchall()
    candidates = {r["id"]: row_to_dict(r) for r in rows}

    # Full-text relevance for the residual terms.
    text_scores: dict[str, float] = {}
    match_expr = _fts_query(intent.terms)
    if match_expr:
        fts_rows = conn.execute(
            "SELECT entry_id,"
            " bm25(entries_fts, 0.0, 8.0, 6.0, 3.0, 1.0) AS score"
            " FROM entries_fts WHERE entries_fts MATCH ?"
            " ORDER BY score LIMIT 500",
            (match_expr,),
        ).fetchall()
        for row in fts_rows:
            # bm25() is negative, with more-negative meaning a better match.
            text_scores[row["entry_id"]] = -float(row["score"])

        if not intent.competitor and not effective_category:
            # Free-text-only query: the matched set is the candidate set.
            missing = [i for i in text_scores if i not in candidates]
            for entry_id in missing:
                found = conn.execute(
                    "SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
                if found:
                    candidates[entry_id] = row_to_dict(found)
            candidates = {i: e for i, e in candidates.items() if i in text_scores}

    top_text = max(text_scores.values(), default=0.0) or 1.0

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

        relevance = text_scores.get(entry_id, 0.0)
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


def retrieve_passages(conn: sqlite3.Connection, question: str,
                      entry_id: str = "", competitor: str = "",
                      limit: int = 8) -> list[dict[str, Any]]:
    """Fetch the passages most likely to answer a question.

    This is what replaces blindly sending the first 6000 characters of a
    document to the model. Long files stay answerable because the relevant
    passage is retrieved wherever it sits in the file.
    """
    terms = [t for t in normalise(question).split() if len(t) > 2]
    match_expr = _fts_query(terms)
    if not match_expr:
        return []

    clauses, params = ["chunks_fts MATCH ?"], [match_expr]
    if entry_id:
        clauses.append("c.entry_id = ?")
        params.append(entry_id)
    elif competitor:
        clauses.append("e.competitor_key = ?")
        params.append(normalise(competitor))

    rows = conn.execute(
        "SELECT c.chunk_id, c.entry_id, c.text,"
        " bm25(chunks_fts) AS score, e.title, e.competitor, e.category"
        " FROM chunks_fts c JOIN entries e ON e.id = c.entry_id"
        f" WHERE {' AND '.join(clauses)}"
        " ORDER BY score LIMIT ?",
        (*params, limit),
    ).fetchall()

    return [{
        "entry_id": r["entry_id"],
        "title": r["title"],
        "competitor": r["competitor"],
        "category": r["category"],
        "text": r["text"],
        "score": round(-float(r["score"]), 4),
    } for r in rows]
