"""Claude integration, server side.

The prototype called api.anthropic.com straight from the browser with no
x-api-key and no anthropic-version header, so every Analyze and every Ask
returned 401. Moving the call here fixes that and keeps the key out of page
source, where anyone could have read it.

Answers are grounded in passages retrieved from the library rather than the
first few thousand characters of a file, and every answer carries the sources
it used so a claim can be checked before it reaches a customer conversation.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .competitors import threatened_products
from .config import Config

# Structured shapes. Constraining the model beats parsing prose.
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Two or three sentence executive summary.",
        },
        "insights": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Three to five sharp, specific insights.",
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Soft spots an IA seller can probe.",
        },
        "how_to_win": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete plays that beat this competitor.",
        },
        "segments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Verticals or segments where this competitor is strong.",
        },
        "threatened_products": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Impact Analytics products most exposed.",
        },
    },
    "required": ["summary", "insights", "weaknesses", "how_to_win"],
    "additionalProperties": False,
}


# ─── head to head scoring ──────────────────────────────────────────────────

# Fixed dimensions so two battlecards are comparable. Every score reads
# "higher is better for that vendor", including cost, where a high score means
# a lower total cost of ownership.
SCORE_DIMENSIONS: list[tuple[str, str, str]] = [
    ("retail_native_depth", "Retail-native depth",
     "Purpose built for retail rather than adapted from generic supply chain or planning."),
    ("forecasting", "Forecasting accuracy",
     "Demand forecasting quality at item, store and channel level."),
    ("merchandising", "Merchandising and assortment",
     "Assortment, item, size and pack planning depth."),
    ("pricing_promo", "Pricing, promo and markdown",
     "Price optimisation, promotion planning and markdown execution."),
    ("inventory", "Inventory and replenishment",
     "Allocation, replenishment and inventory productivity."),
    ("speed_to_value", "Speed to value",
     "Time from signature to a measurable business result."),
    ("ai_capability", "AI and agentic capability",
     "Native AI and autonomous decisioning rather than dashboards and reports."),
    ("cost", "Total cost of ownership",
     "Licence, services and internal effort across the contract. Higher is cheaper."),
    ("breadth", "Suite breadth",
     "Coverage across the planning and execution lifecycle."),
    ("retail_proof", "Retail customer proof",
     "Named retail references and demonstrated outcomes."),
]
DIMENSION_KEYS = [key for key, _, _ in SCORE_DIMENSIONS]
DIMENSION_LABELS = {key: label for key, label, _ in SCORE_DIMENSIONS}

# Server-side tools. These run on Anthropic's infrastructure, so there is no
# client-side tool loop to implement. The _20260209 versions add dynamic
# filtering on Opus 5, which trims search results before they reach context.
RESEARCH_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]

RESEARCHER_SYSTEM = (
    "You are a competitive intelligence researcher at Impact Analytics, a "
    "retail AI company competing in retail planning, merchandising, pricing "
    "and inventory.\n\n"
    "Research the named competitor using current public sources. Prioritise "
    "primary sources: the vendor's own site and documentation, filings, "
    "customer case studies, analyst coverage and credible trade press. "
    "Prefer recent material and say when a source is dated.\n\n"
    "Report only what the sources support. Where a fact is contested or "
    "unclear, say so rather than resolving it silently. Do not use em dashes "
    "or en dashes."
)


# A battlecard is only useful if a seller can act on it in a live call, so the
# shape is fixed rather than left to prose. Every section is a field the UI can
# render on its own.
BATTLECARD_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "One sentence a seller could say out loud to frame the matchup.",
        },
        "who_they_are": {
            "type": "string",
            "description": "Two or three sentences: what they sell and who buys it.",
        },
        "where_they_win": {
            "type": "array", "items": {"type": "string"},
            "description": "Three to five honest strengths. Do not soften them.",
        },
        "where_they_are_weak": {
            "type": "array", "items": {"type": "string"},
            "description": "Three to five soft spots grounded in the source material.",
        },
        "how_we_win": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "play": {"type": "string", "description": "The move to make."},
                    "why_it_works": {"type": "string"},
                },
                "required": ["play", "why_it_works"],
                "additionalProperties": False,
            },
            "description": "Three to five concrete plays, not slogans.",
        },
        "discovery_questions": {
            "type": "array", "items": {"type": "string"},
            "description": "Questions that surface this competitor's weakness in the buyer's own words.",
        },
        "objection_handling": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "objection": {"type": "string", "description": "What the buyer says."},
                    "response": {"type": "string", "description": "How to answer it."},
                },
                "required": ["objection", "response"],
                "additionalProperties": False,
            },
        },
        "landmines": {
            "type": "array", "items": {"type": "string"},
            "description": "Ground to avoid, where this competitor is genuinely stronger.",
        },
        "pricing_and_deployment": {
            "type": "string",
            "description": "What the material says about their commercial and implementation posture. Say so if it says nothing.",
        },
        "proof_points": {
            "type": "array", "items": {"type": "string"},
            "description": "Named customers, metrics or references found in the material.",
        },
        "threatened_products": {
            "type": "array", "items": {"type": "string"},
            "description": "Impact Analytics products most exposed.",
        },
        "intel_gaps": {
            "type": "array", "items": {"type": "string"},
            "description": "What the library does not cover and should. Be specific.",
        },
        "confidence": {
            "type": "string", "enum": ["high", "medium", "low"],
            "description": "How well the source material supports this battlecard.",
        },
        "verdict": {
            "type": "string",
            "description": "Two sentences on where Impact Analytics genuinely stands against this competitor.",
        },
        "scorecard": {
            "type": "array",
            "minItems": 1,
            "description": (
                "Exactly one entry for each of the ten dimensions, no repeats "
                "and none omitted. The count cannot be expressed in the schema, "
                "so it is enforced in the prompt and checked after the call."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "enum": DIMENSION_KEYS},
                    "ia_score": {
                        "type": "number",
                        "description": "Impact Analytics, 0 to 10. Higher is better.",
                    },
                    "competitor_score": {
                        "type": "number",
                        "description": "The competitor, 0 to 10. Higher is better.",
                    },
                    "weight": {
                        "type": "number",
                        "description": "How much this dimension matters in a real deal, 1 to 5.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "One or two sentences justifying both scores.",
                    },
                    "evidence": {
                        "type": "string",
                        "enum": ["library", "research", "both", "inference"],
                        "description": "Where the judgement came from. Use inference only when neither source covers it.",
                    },
                },
                "required": ["dimension", "ia_score", "competitor_score",
                             "weight", "rationale", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "headline", "who_they_are", "where_they_win", "where_they_are_weak",
        "how_we_win", "discovery_questions", "objection_handling", "landmines",
        "pricing_and_deployment", "intel_gaps", "confidence", "verdict",
        "scorecard",
    ],
    "additionalProperties": False,
}

# A single query retrieves a single theme. A battlecard needs several, so the
# library is swept once per theme and the results merged.
BATTLECARD_THEMES = {
    "positioning": "positioning differentiation value proposition market category",
    "strengths": "strengths advantages leader capabilities best in class",
    "weaknesses": "weaknesses gaps limitations criticism complaints problems",
    "pricing": "pricing cost licence total cost of ownership budget expensive",
    "deployment": "implementation deployment timeline onboarding integration migration",
    "customers": "customers clients references logos case study retailers wins losses",
    "product": "forecasting assortment allocation replenishment markdown promotion planning",
    "technology": "AI machine learning agentic architecture cloud platform data model",
}

ANALYST_SYSTEM = (
    "You are a competitive intelligence analyst at Impact Analytics, a retail "
    "AI company. Its products are ItemSmart, PlanSmart, AssortSmart, "
    "PriceSmart, MarkSmart, PromoSmart, InventorySmart, SizeSmart, StoreSmart, "
    "AttributeSmart and CortexEye.\n\n"
    "Write for a seller heading into a live deal. Be direct and concrete. "
    "Ground every claim in the supplied document text. When the document does "
    "not support a claim, leave it out rather than inferring it. Do not use em "
    "dashes or en dashes."
)


class LLMUnavailable(Exception):
    """Raised when the model cannot be reached or is not configured."""


def available() -> bool:
    return Config.ai_enabled()


def _client():
    if not Config.ai_enabled():
        raise LLMUnavailable(
            "AI features are off because ANTHROPIC_API_KEY is not set on the "
            "server. Search, upload and the library all work without it.")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailable("Server is missing the anthropic package.") from exc
    return anthropic.Anthropic(api_key=Config.api_key())


def _extract_sources(response: Any) -> list[dict[str, str]]:
    """Collect the web pages a research call actually consulted.

    Walks the server tool result blocks defensively, because a block shape that
    changes should cost the citation list, never the whole battlecard.
    """
    found: dict[str, dict[str, str]] = {}
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", "") != "web_search_tool_result":
            continue
        for item in getattr(block, "content", []) or []:
            url = getattr(item, "url", None)
            if not url:
                continue
            found.setdefault(url, {
                "url": url,
                "title": getattr(item, "title", "") or url,
            })
    return list(found.values())


def _call(system: str, prompt: str, max_tokens: int = 4000,
          schema: dict[str, Any] | None = None,
          tools: list[dict[str, Any]] | None = None,
          return_response: bool = False) -> Any:
    """One Claude call. Returns parsed JSON when a schema is supplied."""
    client = _client()   # raises LLMUnavailable before anthropic is needed
    import anthropic

    kwargs: dict[str, Any] = {
        "model": Config.MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "adaptive"},
    }
    if schema is not None:
        kwargs["output_config"] = {
            "format": {
                "type": "json_schema",
                "schema": sanitise_schema(schema),
            }
        }
    if tools:
        # Server-side tools execute on Anthropic's infrastructure, so the
        # response returns complete and there is no tool loop to run here.
        kwargs["tools"] = tools

    try:
        response = client.messages.create(**kwargs)
    except anthropic.AuthenticationError as exc:
        raise LLMUnavailable(
            "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in "
            f"the Render dashboard. ({_api_message(exc)})") from exc
    except anthropic.RateLimitError as exc:
        raise LLMUnavailable(
            f"Rate limited by the Anthropic API. Retry shortly. "
            f"({_api_message(exc)})") from exc
    except anthropic.APIStatusError as exc:
        # The API's own message names the real cause: an unavailable model, an
        # exhausted credit balance, a disabled feature. Swallowing it and
        # printing only a status code leaves nothing to act on.
        raise LLMUnavailable(
            f"Anthropic API error {exc.status_code}: {_api_message(exc)}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMUnavailable(
            f"Could not reach the Anthropic API. ({exc})") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise LLMUnavailable("The model declined to answer this request.")

    text = "".join(b.text for b in response.content
                   if getattr(b, "type", "") == "text").strip()
    payload = text if schema is None else _parse_json(text)
    if return_response:
        return payload, response
    return payload


# Structured output accepts a subset of JSON Schema. These keywords are pure
# validation and are safe to strip, because the response is validated in Python
# anyway. Sending any of them is a 400 with no output at all, which is a far
# worse outcome than not declaring the constraint.
_DROPPABLE_SCHEMA_KEYS = frozenset({
    "maxItems", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "minLength", "maxLength", "uniqueItems", "minProperties",
    "maxProperties", "minContains", "maxContains",
})
# These change the shape of what is accepted, so dropping them silently would
# alter meaning. They are refused instead.
_REFUSED_SCHEMA_KEYS = frozenset({"oneOf", "not", "if", "then", "else"})


def sanitise_schema(node: Any) -> Any:
    """Strip keywords structured output rejects, recursively.

    minItems above 1 is unsupported and maxItems is unsupported outright, so a
    fixed-length array cannot be expressed in the schema. Such counts are
    stated in the prompt and enforced after the response instead.
    """
    if isinstance(node, list):
        return [sanitise_schema(item) for item in node]
    if not isinstance(node, dict):
        return node

    refused = _REFUSED_SCHEMA_KEYS & node.keys()
    if refused:
        raise LLMUnavailable(
            f"Schema uses {', '.join(sorted(refused))}, which structured "
            "output does not support. Use anyOf instead.")

    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROPPABLE_SCHEMA_KEYS:
            continue
        if key == "minItems":
            # Only 0 and 1 are accepted. Anything higher becomes "at least one".
            try:
                cleaned[key] = 1 if float(value) >= 1 else 0
            except (TypeError, ValueError):
                continue
            continue
        cleaned[key] = sanitise_schema(value)

    # Objects must carry additionalProperties: false, and true is rejected.
    if cleaned.get("type") == "object" and "properties" in cleaned:
        cleaned["additionalProperties"] = False
    return cleaned


def _api_message(exc: Any) -> str:
    """Pull the human-readable reason out of an SDK error."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    message = getattr(exc, "message", None)
    return str(message or exc)


def _parse_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMUnavailable("The model returned a response that could not be parsed.")


def _format_passages(passages: list[dict[str, Any]]) -> str:
    blocks = []
    for index, passage in enumerate(passages, start=1):
        header = f"[{index}] {passage['title']}"
        if passage.get("competitor"):
            header += f" (competitor: {passage['competitor']})"
        blocks.append(f"{header}\n{passage['text']}")
    return "\n\n---\n\n".join(blocks)


def analyse_document(text: str, competitor: str = "",
                     title: str = "") -> dict[str, Any]:
    """Extract a structured competitor profile from a document."""
    # Configuration is the more fundamental blocker, so report it first.
    # Otherwise a short file hides the fact that AI is switched off entirely.
    if not Config.ai_enabled():
        raise LLMUnavailable(
            "AI features are off because ANTHROPIC_API_KEY is not set on the "
            "server. Search, upload and the library all work without it.")
    if not text or len(text.strip()) < 40:
        raise LLMUnavailable("This document is too short to analyse.")

    # Long documents are sampled from the head, middle and tail rather than
    # truncated, so a conclusion buried at the end is not silently discarded.
    budget = 60000
    if len(text) > budget:
        third = budget // 3
        text = (text[:third]
                + "\n\n[... middle of document omitted ...]\n\n"
                + text[len(text) // 2: len(text) // 2 + third]
                + "\n\n[... omitted ...]\n\n"
                + text[-third:])

    prompt = (
        f"Competitor: {competitor or 'unknown'}\n"
        f"Document title: {title or 'untitled'}\n\n"
        f"DOCUMENT:\n{text}\n\n"
        "Analyse this competitor document for an Impact Analytics seller."
    )
    result = _call(ANALYST_SYSTEM, prompt, max_tokens=4000, schema=ANALYSIS_SCHEMA)

    # The registry knows the product mapping, so fill it in when the model
    # leaves it empty rather than making the seller work it out.
    if competitor and not result.get("threatened_products"):
        mapped = threatened_products(competitor)
        if mapped:
            result["threatened_products"] = mapped
    return result


def answer_question(question: str, passages: list[dict[str, Any]]) -> dict[str, Any]:
    """Answer a question strictly from retrieved passages, with citations."""
    if not Config.ai_enabled():
        raise LLMUnavailable(
            "AI features are off because ANTHROPIC_API_KEY is not set on the "
            "server. Search, upload and the library all work without it.")
    if not passages:
        raise LLMUnavailable(
            "Nothing in the library matches that question. Add a document for "
            "this competitor, or rephrase the question.")

    prompt = (
        f"PASSAGES FROM THE LIBRARY:\n\n{_format_passages(passages)}\n\n"
        f"QUESTION: {question}\n\n"
        "Answer using only the passages above. Cite the passages you use with "
        "their bracketed numbers, like [1] or [2]. If the passages do not "
        "answer the question, say exactly what is missing."
    )
    answer = _call(ANALYST_SYSTEM, prompt, max_tokens=2000)

    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)
                    if 0 < int(n) <= len(passages)})
    return {
        "answer": answer,
        "citations": [{
            "n": n,
            "entry_id": passages[n - 1]["entry_id"],
            "title": passages[n - 1]["title"],
            "competitor": passages[n - 1]["competitor"],
        } for n in cited],
        "passages_used": len(passages),
    }


def research_competitor(competitor: str, library_context: str = "",
                        max_tokens: int = 8000) -> dict[str, Any]:
    """Phase one: research the competitor against live public sources.

    Kept separate from synthesis on purpose. Tool use needs several model turns
    and structured output constrains the final one, so combining them in a
    single call is the fragile arrangement. Splitting them also means a
    research failure degrades to a library-only battlecard instead of losing
    the whole card.
    """
    if not Config.ai_enabled():
        raise LLMUnavailable(
            "AI features are off because ANTHROPIC_API_KEY is not set on the "
            "server.")

    prompt = (
        f"Research {competitor} as a competitor to Impact Analytics in retail "
        f"planning, merchandising, pricing and inventory.\n\n"
        "Cover, and label, each of these:\n"
        "1. What they sell and how they position it.\n"
        "2. Recent product and AI announcements, with dates.\n"
        "3. Named retail customers, wins and any public losses.\n"
        "4. Pricing signals and total cost of ownership commentary.\n"
        "5. Implementation timelines and delivery model.\n"
        "6. Analyst and customer criticism, stated plainly.\n"
        "7. Where they are genuinely strong. Do not soften this.\n\n"
        + (f"The internal library already holds the following. Treat it as "
           f"context to extend and verify, not as fact to repeat:\n"
           f"{library_context[:6000]}\n\n" if library_context else "")
        + "Write a factual brief. Attribute each claim to its source."
    )

    brief, response = _call(RESEARCHER_SYSTEM, prompt, max_tokens=max_tokens,
                            tools=RESEARCH_TOOLS, return_response=True)
    return {"brief": brief, "sources": _extract_sources(response)}


def normalise_scorecard(scorecard: Any) -> list[dict[str, Any]]:
    """Clean the model's scorecard into something the UI can trust.

    Unknown or repeated dimensions are dropped, scores are clamped to the
    stated 0 to 10 range and weights to 1 to 5, and rows are ordered so the
    competitor's strongest dimensions come first. A seller reads the threats
    before the wins.
    """
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for row in scorecard or []:
        if not isinstance(row, dict):
            continue
        key = row.get("dimension")
        if key not in DIMENSION_LABELS or key in seen:
            continue
        seen.add(key)
        row = dict(row)
        row["label"] = DIMENSION_LABELS[key]
        for field in ("ia_score", "competitor_score"):
            try:
                value = float(row.get(field) or 0)
            except (TypeError, ValueError):
                value = 0.0
            row[field] = max(0.0, min(10.0, round(value, 1)))
        try:
            weight = float(row.get("weight") or 1)
        except (TypeError, ValueError):
            weight = 1.0
        row["weight"] = max(1.0, min(5.0, weight))
        if row.get("evidence") not in ("library", "research", "both", "inference"):
            row["evidence"] = "inference"
        rows.append(row)
    rows.sort(key=lambda r: (r["competitor_score"] - r["ia_score"], r["weight"]),
              reverse=True)
    return rows


def score_totals(scorecard: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute weighted totals in Python, not in the model.

    The model judges each dimension; the arithmetic is done here so the
    headline number is reproducible from the visible rows and cannot drift
    from them.
    """
    rows = [r for r in scorecard
            if isinstance(r, dict) and r.get("dimension") in DIMENSION_LABELS]
    if not rows:
        return {"ia": 0.0, "competitor": 0.0, "gap": 0.0, "verdict_key": "unknown"}

    total_weight = sum(max(float(r.get("weight") or 1), 0.1) for r in rows)
    def weighted(field: str) -> float:
        return sum(float(r.get(field) or 0) * max(float(r.get("weight") or 1), 0.1)
                   for r in rows) / total_weight

    ia = round(weighted("ia_score"), 1)
    competitor = round(weighted("competitor_score"), 1)
    gap = round(ia - competitor, 1)
    if gap >= 1.5:
        verdict_key = "advantage"
    elif gap <= -1.5:
        verdict_key = "behind"
    else:
        verdict_key = "close"
    return {"ia": ia, "competitor": competitor, "gap": gap,
            "verdict_key": verdict_key}


def build_battlecard(competitor: str, passages: list[dict[str, Any]],
                     research: dict[str, Any] | None = None) -> dict[str, Any]:
    """Phase two: synthesise a scored battlecard from library and research."""
    if not Config.ai_enabled():
        raise LLMUnavailable(
            "AI features are off because ANTHROPIC_API_KEY is not set on the "
            "server. Search, upload and the library all work without it.")
    if not passages and not (research and research.get("brief")):
        raise LLMUnavailable(
            f"Nothing to build from. The library holds no documents on "
            f"{competitor} and research returned nothing.")

    products = ", ".join(threatened_products(competitor)) or "the IA portfolio"
    library_block = (_format_passages(passages) if passages
                     else "The library holds no documents on this competitor.")
    research_block = (research or {}).get("brief") or (
        "No external research was available for this card.")

    dimension_lines = "\n".join(
        f"- {key}: {label}. {definition}" for key, label, definition in SCORE_DIMENSIONS)

    prompt = (
        f"INTERNAL LIBRARY MATERIAL ON {competitor}:\n\n{library_block}\n\n"
        f"EXTERNAL RESEARCH ON {competitor}:\n\n{research_block}\n\n"
        f"Build a scored sales battlecard for Impact Analytics against "
        f"{competitor}. The IA products most exposed are: {products}.\n\n"
        f"Score both vendors on every one of these ten dimensions:\n"
        f"{dimension_lines}\n\n"
        "Scoring rules:\n"
        "- Every score runs 0 to 10 and higher is always better for that "
        "vendor, cost included, where a high score means a lower total cost "
        "of ownership.\n"
        "- Weight each dimension 1 to 5 by how much it decides a real deal.\n"
        "- Score the competitor above Impact Analytics wherever the evidence "
        "says so. A scorecard that flatters us on every dimension is not "
        "credible and loses deals.\n"
        "- Set evidence to library, research, both, or inference. Use "
        "inference only when neither source covers the dimension, and keep "
        "those scores near the middle.\n\n"
        "Content rules:\n"
        "- Cite internal passages by their bracketed numbers, such as [1].\n"
        "- Attribute external claims to their source in the text.\n"
        "- Discovery questions must be open questions a buyer would answer, "
        "not leading questions naming the competitor's flaw.\n"
        "- Where evidence is thin, say so in intel_gaps and lower the "
        "confidence rather than inventing detail."
    )

    card = _call(ANALYST_SYSTEM, prompt, max_tokens=12000,
                 schema=BATTLECARD_SCHEMA)

    rows = normalise_scorecard(card.get("scorecard"))
    card["scorecard"] = rows
    # The schema cannot require exactly ten entries, so a short scorecard is
    # possible. Say which dimensions went unscored rather than quietly showing
    # a smaller table that looks complete.
    missing = [DIMENSION_LABELS[k] for k in DIMENSION_KEYS
               if k not in {r["dimension"] for r in rows}]
    card["missing_dimensions"] = missing
    if missing:
        gaps = list(card.get("intel_gaps") or [])
        gaps.append("Not scored on: " + ", ".join(missing) + ".")
        card["intel_gaps"] = gaps
    card["totals"] = score_totals(rows)

    if not card.get("threatened_products"):
        mapped = threatened_products(competitor)
        if mapped:
            card["threatened_products"] = mapped
    card["competitor"] = competitor
    card["sources"] = sorted({p["title"] for p in passages})
    card["research_sources"] = (research or {}).get("sources", [])
    card["researched"] = bool((research or {}).get("brief"))
    return card


# Minimal schema for the structured-output probe. Kept tiny so the check costs
# almost nothing while still exercising the same code path as a battlecard.
_PROBE_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def self_test() -> dict[str, Any]:
    """Prove the Claude integration works, and say precisely what fails if not.

    The probes run separately because they fail for different reasons. A plain
    message failing points at the key, the model or the credit balance. A plain
    message succeeding while the structured probe fails isolates structured
    outputs, which Analyze and the battlecard depend on. Web search is probed
    too, since researched battlecards need it and nothing else exercises it.
    """
    import time

    report: dict[str, Any] = {
        "key_present": Config.ai_enabled(),
        "key_source": Config.api_key_with_source()[1],
        "model": Config.MODEL,
        "checks": [],
    }
    if not Config.ai_enabled():
        report["ok"] = False
        report["checks"].append({
            "name": "api key configured", "ok": False,
            "error": "ANTHROPIC_API_KEY is not set on the server.",
        })
        return report

    # Every probe keeps adaptive thinking on so it runs the same path as the
    # real features, with a generous budget so a probe cannot run out of room
    # and report a failure the real feature would not have hit.
    probes = (
        ("plain message", lambda: _call(
            "Reply with the single word: ready.", "Say ready.", max_tokens=1024)),
        ("structured output", lambda: _call(
            "Return JSON only.", 'Return {"ok": true}.',
            max_tokens=1024, schema=_PROBE_SCHEMA)),
        ("web search (research)", lambda: _call(
            "Answer in one short sentence.",
            "Search the web for the founding year of Blue Yonder.",
            max_tokens=4096, tools=RESEARCH_TOOLS)),
    )

    for name, run in probes:
        started = time.monotonic()
        try:
            result = run()
            report["checks"].append({
                "name": name, "ok": True,
                "ms": int((time.monotonic() - started) * 1000),
                "sample": str(result)[:120],
            })
        except LLMUnavailable as exc:
            report["checks"].append({
                "name": name, "ok": False,
                "ms": int((time.monotonic() - started) * 1000),
                "error": str(exc),
            })
        except Exception as exc:
            report["checks"].append({
                "name": name, "ok": False,
                "ms": int((time.monotonic() - started) * 1000),
                "error": f"{type(exc).__name__}: {exc}",
            })

    report["ok"] = all(check["ok"] for check in report["checks"])
    return report
