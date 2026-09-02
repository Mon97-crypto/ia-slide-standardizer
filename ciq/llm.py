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
    },
    "required": [
        "headline", "who_they_are", "where_they_win", "where_they_are_weak",
        "how_we_win", "discovery_questions", "objection_handling", "landmines",
        "pricing_and_deployment", "intel_gaps", "confidence",
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
    return anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)


def _call(system: str, prompt: str, max_tokens: int = 4000,
          schema: dict[str, Any] | None = None) -> Any:
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
                "schema": schema,
            }
        }

    try:
        response = client.messages.create(**kwargs)
    except anthropic.AuthenticationError as exc:
        raise LLMUnavailable(
            "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from exc
    except anthropic.RateLimitError as exc:
        raise LLMUnavailable("Rate limited by the Anthropic API. Retry shortly.") from exc
    except anthropic.APIStatusError as exc:
        raise LLMUnavailable(f"Anthropic API error {exc.status_code}.") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMUnavailable("Could not reach the Anthropic API.") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise LLMUnavailable("The model declined to answer this request.")

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if schema is None:
        return text
    return _parse_json(text)


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


def build_battlecard(competitor: str,
                     passages: list[dict[str, Any]]) -> dict[str, Any]:
    """Draft a battlecard from everything the library holds on a competitor."""
    if not Config.ai_enabled():
        raise LLMUnavailable(
            "AI features are off because ANTHROPIC_API_KEY is not set on the "
            "server. Search, upload and the library all work without it.")
    if not passages:
        raise LLMUnavailable(
            f"The library holds nothing on {competitor} yet. Add a document "
            "for them first.")

    products = ", ".join(threatened_products(competitor)) or "the IA portfolio"
    sources = sorted({p["title"] for p in passages})
    prompt = (
        f"SOURCE MATERIAL ON {competitor}, drawn from "
        f"{len(sources)} documents in the library:\n\n"
        f"{_format_passages(passages)}\n\n"
        f"Build a sales battlecard for Impact Analytics against {competitor}. "
        f"The IA products most exposed are: {products}.\n\n"
        "Rules:\n"
        "- Ground every claim in the passages above. Cite them inline with "
        "bracketed numbers such as [1].\n"
        "- Be honest about where the competitor is strong. A battlecard that "
        "only flatters us loses deals.\n"
        "- Discovery questions must be open questions a buyer would answer, "
        "not leading questions that name the competitor's flaw.\n"
        "- Where the material is thin, say so in intel_gaps and lower the "
        "confidence rather than inventing detail."
    )
    card = _call(ANALYST_SYSTEM, prompt, max_tokens=8000,
                 schema=BATTLECARD_SCHEMA)

    if not card.get("threatened_products"):
        mapped = threatened_products(competitor)
        if mapped:
            card["threatened_products"] = mapped
    card["competitor"] = competitor
    card["sources"] = sources
    return card
