"""Anthropic-powered battlecard generation and the in-app chat assistant.

Two entry points:

- `generate(competitor, product, depth)` researches a competitor against an
  Impact Analytics product and returns a card payload ready for the builder.
- `chat_stream(history, card)` answers questions about the card in the open
  builder, and can hand back a patch the UI applies.

Grounding is the whole design. Claude receives the Impact Analytics product facts
and the brand writing rules as ground truth, and is told in the system prompt to
mark any competitor claim it cannot source. Unsourced capability ratings come back
as `unknown`, which the deck renders as "Unclear" with "Ask the question, do not
assert the gap". Curated cards win over generated ones wherever they exist, so the
model fills gaps rather than overwriting research.
"""

from __future__ import annotations

import json
import logging
import os
import re

from . import attributesmart, library
from .brand import PRODUCT_SOLUTIONS, SOLUTION_LABELS
from .schema import DEPTHS, DEFAULT_DEPTH, RATING_VALUES

log = logging.getLogger(__name__)

MODEL = 'claude-opus-5'
# Server side web search, so competitor claims can carry a real source. This runs
# on Anthropic's infrastructure, not from this container.
WEB_SEARCH_TOOL = {'type': 'web_search_20260209', 'name': 'web_search', 'max_uses': 8}

RESEARCH_MAX_TOKENS = 32000
STRUCTURE_MAX_TOKENS = 32000
CHAT_MAX_TOKENS = 8000

# Claude Opus 5 token pricing, USD per million tokens. Cache writes bill at about
# 1.25x input and cache reads at about 0.1x.
PRICING = {'input': 5.00, 'output': 25.00, 'cache_write': 6.25, 'cache_read': 0.50}

# Economy mode trades thoroughness for a predictable bill: shallower effort, fewer
# searches and tighter ceilings. Useful for a first run on a small budget.
# `max_tokens` is only a ceiling. Output bills for what is generated, so a
# generous cap costs nothing and avoids truncating a long card. Economy saves
# through shallower effort and fewer searches instead.
ECONOMY = {'effort': 'low', 'searches': 3, 'max_tokens': 24000}
STANDARD = {'effort': 'high', 'searches': 8, 'max_tokens': RESEARCH_MAX_TOKENS}


def _search_tool(max_uses: int) -> dict:
    return {'type': 'web_search_20260209', 'name': 'web_search', 'max_uses': max_uses}


def usage_cost(usage) -> dict:
    """Turn one response's usage into token counts and a dollar figure.

    Token cost only. Web search bills a separate per-search fee that does not
    appear in `usage`, so the number here is a floor, not the whole invoice.
    """
    def count(name):
        return int(getattr(usage, name, 0) or 0)

    plain = count('input_tokens')
    cache_write = count('cache_creation_input_tokens')
    cache_read = count('cache_read_input_tokens')
    output = count('output_tokens')
    dollars = (plain * PRICING['input']
               + cache_write * PRICING['cache_write']
               + cache_read * PRICING['cache_read']
               + output * PRICING['output']) / 1_000_000.0
    return {'input': plain, 'cache_write': cache_write, 'cache_read': cache_read,
            'output': output, 'usd': round(dollars, 4)}


def add_cost(total: dict, usage) -> dict:
    """Accumulate usage from several calls into one running total."""
    one = usage_cost(usage)
    for key in ('input', 'cache_write', 'cache_read', 'output'):
        total[key] = total.get(key, 0) + one[key]
    total['usd'] = round(total.get('usd', 0) + one['usd'], 4)
    total['calls'] = total.get('calls', 0) + 1
    return total


class AIUnavailable(RuntimeError):
    """Raised when no Anthropic credential is configured."""


def available() -> bool:
    """True when a credential actually resolved.

    `anthropic.Anthropic()` constructs happily with no key and only fails at
    request time, so constructing a client proves nothing. This checks that a
    credential resolved: an API key, an auth token, or a profile on disk, which
    the SDK reads at request time.
    """
    try:
        client = _client()
    except AIUnavailable:
        return False
    if getattr(client, 'api_key', None) or getattr(client, 'auth_token', None):
        return True
    profile_dir = os.path.expanduser('~/.config/anthropic')
    return os.path.isdir(profile_dir) and bool(os.listdir(profile_dir))


def _client():
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise AIUnavailable('The anthropic package is not installed.') from exc
    try:
        return anthropic.Anthropic()
    except Exception as exc:
        raise AIUnavailable(
            'No Anthropic credential found. Set ANTHROPIC_API_KEY.') from exc


# ─── Ground truth handed to the model ───────────────────────────────────────────

def _product_facts(product: str) -> str:
    """Everything the repository knows about one IA product, as prose."""
    lines = []
    for entry in library.PRODUCT_CATALOG:
        if entry['name'].lower() == (product or '').lower():
            lines.append('%s sits in the %s solution. %s'
                         % (entry['name'], SOLUTION_LABELS[entry['solution']],
                            entry['blurb']))
            break

    if (product or '').lower() == 'attributesmart':
        lines.append('\nVerified AttributeSmart mechanism, from the AttributeSmart '
                     'NRF 2026 deck. Treat every line as fact:')
        for key, text in attributesmart.MECHANISM.items():
            lines.append('- %s: %s' % (key, text))
        lines.append('\nVerified AttributeSmart results. Cite each as "%s":'
                     % attributesmart.IA_CITATION)
        for row in attributesmart.PROOF_POINTS:
            lines.append('- %s %s. %s' % (row['stat'], row['label'], row['detail']))
        lines.append('\nBuyer pain these results answer:')
        for pain in attributesmart.PAIN_POINTS:
            lines.append('- %s' % pain)
        lines.append('\nAttributeSmart GENERATES attributes from images, labels and '
                     'text. Most retail planning suites only CONSUME attributes. '
                     'Where that is true of this competitor, the card should say so '
                     'and position alongside them rather than against them.')
    return '\n'.join(lines) or 'No curated facts for this product yet.'


SYSTEM_RULES = """You write competitive battlecards for Impact Analytics, a retail AI company.

HONESTY RULES. These outrank everything else, including making the card look strong.

1. Never state a capability, number, customer, price or roadmap item for a
   competitor unless a source you actually found supports it. A battlecard that
   overstates a rival's gap loses the deal the moment the buyer corrects it.
2. When the public record is silent on a capability, set that competitor rating to
   "unknown" and write a note telling the seller to ask. Do not guess, and do not
   infer a gap from absence of evidence.
3. Impact Analytics facts come from the ground truth below. Do not invent IA
   capabilities or results. If a fact is not in the ground truth, leave it out.
4. Every proof point needs a source: a public URL, or the exact internal citation
   string given in the ground truth.
5. Be honest about competitor strengths. Credibility in the rest of the card
   depends on an accurate read of what they do well.

BRAND WRITING RULES, non negotiable.

- Direct tone, active voice, lead with the point.
- No em dashes and no en dashes anywhere. Use commas, periods or shorter sentences.
- Never end a sentence with a preposition.
- Plain language, readability grade 9 or lower.
- Statistics must be from 2025 or later.
- No exaggeration, no superlatives. The data carries the argument."""


def _system_prompt(product: str, competitor: str) -> list:
    """System blocks, with the stable part cached.

    The rules and product facts are identical across requests for one product, so
    they sit in their own cached block ahead of the volatile competitor name.
    """
    stable = '%s\n\nIMPACT ANALYTICS GROUND TRUTH\n\n%s' % (
        SYSTEM_RULES, _product_facts(product))
    return [
        {'type': 'text', 'text': stable, 'cache_control': {'type': 'ephemeral'}},
        {'type': 'text', 'text': 'This card covers %s.' % competitor},
    ]


# ─── Structured output schema ───────────────────────────────────────────────────
# Deliberately a subset of the full card. Fields the model should not decide,
# such as brand options and distribution, are set in code afterwards.

_STR = {'type': 'string'}
_RATING = {'type': 'string', 'enum': list(RATING_VALUES)}


def _array(item, *required):
    return {'type': 'array', 'items': {
        'type': 'object',
        'properties': item,
        'required': list(required or item.keys()),
        'additionalProperties': False,
    }}


CARD_SCHEMA = {
    'type': 'object',
    'properties': {
        'competitor_category': _STR,
        'headline': _STR,
        'win_theme': _STR,
        'snapshot': {
            'type': 'object',
            'properties': {
                'headquarters': _STR, 'founded': _STR, 'employees': _STR,
                'ownership': _STR, 'funding': _STR, 'target_segment': _STR,
                'go_to_market': _STR, 'deployment': _STR, 'notable_customers': _STR,
                'recent_moves': {'type': 'array', 'items': _STR},
            },
            'required': ['headquarters', 'founded', 'employees', 'ownership',
                         'funding', 'target_segment', 'go_to_market', 'deployment',
                         'notable_customers', 'recent_moves'],
            'additionalProperties': False,
        },
        'positioning': {
            'type': 'object',
            'properties': {'their_claim': _STR, 'our_claim': _STR, 'wedge': _STR},
            'required': ['their_claim', 'our_claim', 'wedge'],
            'additionalProperties': False,
        },
        'their_strengths': {'type': 'array', 'items': _STR},
        'their_weaknesses': {'type': 'array', 'items': _STR},
        'our_advantages': _array({'title': _STR, 'detail': _STR, 'proof': _STR}),
        'comparison': _array({'capability': _STR, 'ia': _RATING,
                              'competitor': _RATING, 'note': _STR}),
        'objections': _array({'objection': _STR, 'response': _STR, 'proof': _STR}),
        'landmines': _array({'question': _STR, 'why': _STR, 'listen_for': _STR}),
        'discovery': _array({'theme': _STR,
                             'questions': {'type': 'array', 'items': _STR}}),
        'proof_points': _array({'stat': _STR, 'label': _STR, 'detail': _STR,
                                'source': _STR}),
        'talk_track': {
            'type': 'object',
            'properties': {'positioning': _STR, 'elevator': _STR,
                           'discovery_open': _STR, 'trap': _STR},
            'required': ['positioning', 'elevator', 'discovery_open', 'trap'],
            'additionalProperties': False,
        },
        'dos': {'type': 'array', 'items': _STR},
        'donts': {'type': 'array', 'items': _STR},
        'pricing': {
            'type': 'object',
            'properties': {'ia_model': _STR, 'competitor_model': _STR,
                           'notes': {'type': 'array', 'items': _STR}},
            'required': ['ia_model', 'competitor_model', 'notes'],
            'additionalProperties': False,
        },
        'next_steps': {'type': 'array', 'items': _STR},
        'resources': _array({'label': _STR, 'url': _STR}),
    },
    'required': ['competitor_category', 'headline', 'win_theme', 'snapshot',
                 'positioning', 'their_strengths', 'their_weaknesses',
                 'our_advantages', 'comparison', 'objections', 'landmines',
                 'discovery', 'proof_points', 'talk_track', 'dos', 'donts',
                 'pricing', 'next_steps', 'resources'],
    'additionalProperties': False,
}


# ─── Card JSON, parsed rather than grammar constrained ──────────────────────────
# `output_config.format` compiles the schema into a grammar, and CARD_SCHEMA is
# too large for it: the API rejects the request with "The compiled grammar is too
# large". Splitting the schema would only move the ceiling, so the shape is given
# to the model as a contract in the prompt and parsed here instead. `normalize()`
# was always the real validator, coercing every field and dropping anything it
# does not recognise, so nothing downstream relies on the grammar.

_FENCE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$', re.I)


def _parse_card_json(text: str) -> dict:
    """Pull a JSON object out of a model response.

    Tolerates a code fence, a sentence of preamble, and trailing commentary,
    because those are the shapes a model actually produces when it drifts.
    """
    if not text or not text.strip():
        raise ValueError('The model returned nothing to parse.')

    body = _FENCE.sub('', text.strip())
    try:
        data = json.loads(body)
    except ValueError:
        start = body.find('{')
        end = body.rfind('}')
        if start < 0:
            raise ValueError('No JSON object found in the response.')
        if end <= start:
            raise ValueError('The JSON object is incomplete, which usually means '
                             'the response hit max_tokens.')
        data = json.loads(body[start:end + 1])

    if not isinstance(data, dict):
        raise ValueError('The response parsed to %s, not an object.'
                         % type(data).__name__)
    return data


def _shape_contract() -> str:
    """The expected JSON shape, rendered from the one schema definition."""
    return json.dumps(CARD_SCHEMA, indent=1, sort_keys=True)


# ─── Generation ─────────────────────────────────────────────────────────────────

def generate(competitor: str, product: str, depth: str = DEFAULT_DEPTH,
             notes: str = '') -> dict:
    """Research and build a card payload. Raises AIUnavailable without a key."""
    client = _client()
    competitor = (competitor or '').strip()
    product = (product or '').strip()
    if not competitor:
        raise ValueError('Name the competitor.')

    preset = DEPTHS.get(depth, DEPTHS[DEFAULT_DEPTH])
    research = _research(client, competitor, product, notes)
    card = _structure(client, competitor, product, preset, research, notes)

    card = _merge_curated(card, competitor, product)
    card['meta'] = dict(card.get('meta', {}), **{
        'competitor': competitor,
        'ia_product': product,
        'solution': PRODUCT_SOLUTIONS.get(product, 'data_intelligence'),
        'depth': depth if depth in DEPTHS else DEFAULT_DEPTH,
        'distribution': 'internal',
        'audience': 'Sales and solution consulting',
    })
    card['_research'] = research
    return card


def _research_prompt(competitor: str, product: str, notes: str) -> str:
    ask = (
        'Research %(comp)s as a competitor to Impact Analytics %(prod)s.\n\n'
        'Search the public record. Then write a brief covering:\n'
        '1. What %(comp)s actually sells, in their own words, with the source URL.\n'
        '2. Company facts you can source: headquarters, founding year, size, '
        'ownership, funding, target segment, go to market, deployment model.\n'
        '3. Dated news from the last 12 months, each with a source URL.\n'
        '4. What they genuinely do well.\n'
        '5. For each capability, whether the public record says they have it, '
        'partially have it, or says nothing at all. Say "no public claim found" '
        'where that is the truth. Never infer a gap from silence.\n'
        '6. Whether they generate the capability %(prod)s provides, or only '
        'consume its output.\n\n'
        'End with a SOURCES list of every URL you used. If you could not find '
        'something, write "not found" rather than estimating.'
        % {'comp': competitor, 'prod': product or 'the platform'})
    if notes:
        ask += '\n\nExtra context from the seller, treat as unverified input:\n%s' % notes
    return ask


def _research(client, competitor: str, product: str, notes: str) -> str:
    """Phase one: search the public record and write a sourced brief.

    Kept separate from the structuring call because citations and structured
    output formats cannot be combined in one request.
    """
    ask = _research_prompt(competitor, product, notes)
    with client.messages.stream(
        model=MODEL,
        max_tokens=RESEARCH_MAX_TOKENS,
        system=_system_prompt(product, competitor),
        thinking={'type': 'adaptive'},
        output_config={'effort': 'high'},
        tools=[WEB_SEARCH_TOOL],
        messages=[{'role': 'user', 'content': ask}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == 'refusal':
        raise RuntimeError('The research request was declined: %s'
                           % getattr(message.stop_details, 'explanation', 'no reason given'))
    return '\n'.join(block.text for block in message.content
                     if block.type == 'text').strip()


def _structure(client, competitor: str, product: str, preset: dict,
               research: str, notes: str, mode: dict = None, cost: dict = None) -> dict:
    """Phase two: turn the brief into a card payload matching the schema."""
    mode = mode or STANDARD
    caps = preset.get('caps') or {}
    cap_text = ('\n'.join('- at most %d %s' % (cap, key.replace('_', ' '))
                          for key, cap in sorted(caps.items()))
                or '- no row limits, fill every section in full')

    ask = (
        'Turn the brief below into a %(label)s battlecard for %(comp)s.\n\n'
        'Length target for this depth:\n%(caps)s\n\n'
        'Rules for the fields:\n'
        '- their_weaknesses: state what the public record does NOT claim, phrased '
        'so the seller asks rather than asserts. Example: "No published image '
        'extraction capability. Confirm on the call."\n'
        '- comparison: set the ia rating only where the ground truth supports it. '
        'Set the competitor rating to "unknown" unless the brief sourced it, and '
        'write a note telling the seller what to ask.\n'
        '- proof_points: use only Impact Analytics results from the ground truth, '
        'with the exact source string given there.\n'
        '- resources: only URLs that appeared in the brief.\n'
        '- pricing.competitor_model: leave a note that nothing is sourced unless '
        'the brief found published pricing.\n\n'
        'BRIEF\n%(research)s'
        % {'label': preset['label'].lower(), 'comp': competitor,
           'caps': cap_text, 'research': research})
    if notes:
        ask += '\n\nSELLER NOTES\n%s' % notes
    ask += ('\n\nReturn one JSON object and nothing else. No prose before or after, '
            'no code fence. It must match this shape exactly, with every key '
            'present:\n%s' % _shape_contract())
    messages = [{'role': 'user', 'content': ask}]

    with client.messages.stream(
        model=MODEL,
        max_tokens=mode['max_tokens'],
        system=_system_prompt(product, competitor),
        thinking={'type': 'adaptive'},
        output_config={'effort': mode['effort']},
        messages=messages,
    ) as stream:
        message = stream.get_final_message()

    if cost is not None:
        add_cost(cost, message.usage)
    if message.stop_reason == 'refusal':
        raise RuntimeError('The card request was declined.')
    if message.stop_reason == 'max_tokens':
        raise RuntimeError('The card was cut off at the token ceiling. Pick a '
                           'shorter depth, or raise STRUCTURE_MAX_TOKENS.')
    text = ''.join(block.text for block in message.content if block.type == 'text')

    try:
        data = _parse_card_json(text)
    except ValueError as first:
        log.warning('card JSON did not parse (%s), retrying once', first)
        data = _retry_structure(client, messages, text, mode, cost)

    meta_keys = ('competitor_category', 'headline', 'win_theme')
    card = {key: value for key, value in data.items() if key not in meta_keys}
    card['meta'] = {key: data.get(key, '') for key in meta_keys}
    return card


def _retry_structure(client, messages: list, bad: str, mode: dict,
                     cost: dict = None) -> dict:
    """Ask once more for clean JSON, showing the model what came back.

    One retry only. A second failure is a real problem and should surface rather
    than burn more of the budget.
    """
    followup = list(messages) + [
        {'role': 'assistant', 'content': bad[:4000] or '(empty)'},
        {'role': 'user', 'content': 'That did not parse as JSON. Send the same card '
                                    'again as one raw JSON object. Start with { and '
                                    'end with }. No fence, no explanation.'},
    ]
    with client.messages.stream(
        model=MODEL,
        max_tokens=mode['max_tokens'],
        thinking={'type': 'adaptive'},
        output_config={'effort': 'low'},
        messages=followup,
    ) as stream:
        message = stream.get_final_message()
    if cost is not None:
        add_cost(cost, message.usage)
    text = ''.join(block.text for block in message.content if block.type == 'text')
    try:
        return _parse_card_json(text)
    except ValueError as exc:
        raise RuntimeError(
            'The model did not return usable JSON after a retry. %s' % exc) from exc


def _merge_curated(card: dict, competitor: str, product: str) -> dict:
    """Let curated research win over generated content where we have it.

    The four AttributeSmart cards were written against sources by hand. A model
    should not overwrite them, so its output only fills sections the curated card
    leaves thin.
    """
    if (product or '').lower() != 'attributesmart':
        return card
    for name in attributesmart.COMPETITORS:
        if name.lower() != competitor.lower():
            continue
        curated = attributesmart.card_for(name)
        merged = dict(card)
        for key in ('their_strengths', 'their_weaknesses', 'comparison',
                    'objections', 'landmines', 'proof_points', 'our_advantages',
                    'positioning', 'talk_track', 'dos', 'donts', 'resources'):
            if curated.get(key):
                merged[key] = curated[key]
        merged['meta'] = dict(card.get('meta', {}), **curated['meta'])
        merged['_curated'] = True
        return merged
    return card


# ─── Streaming generation, for the browser ──────────────────────────────────────

def generate_events(competitor: str, product: str, depth: str = DEFAULT_DEPTH,
                    notes: str = '', economy: bool = False):
    """Generate a card while yielding progress events.

    Research and structuring each take a while, and a silent connection gets cut
    by the proxy or the worker timeout. Streaming the research text as it arrives
    keeps bytes flowing and gives the seller something to read meanwhile.
    """
    competitor = (competitor or '').strip()
    if not competitor:
        yield {'type': 'error', 'message': 'Name the competitor.'}
        return
    if not available():
        yield {'type': 'error',
               'message': 'No Anthropic credential is configured. Set '
                          'ANTHROPIC_API_KEY on the service, then reload.'}
        return
    try:
        client = _client()
    except AIUnavailable as exc:
        yield {'type': 'error', 'message': str(exc)}
        return

    preset = DEPTHS.get(depth, DEPTHS[DEFAULT_DEPTH])
    mode = ECONOMY if economy else STANDARD
    cost = {}

    try:
        yield {'type': 'status', 'step': 'research',
               'message': 'Searching the public record for %s' % competitor}
        chunks = []
        with client.messages.stream(
            model=MODEL,
            max_tokens=mode['max_tokens'],
            system=_system_prompt(product, competitor),
            thinking={'type': 'adaptive'},
            output_config={'effort': mode['effort']},
            tools=[_search_tool(mode['searches'])],
            messages=[{'role': 'user',
                       'content': _research_prompt(competitor, product, notes)}],
        ) as stream:
            for chunk in stream.text_stream:
                chunks.append(chunk)
                yield {'type': 'research', 'text': chunk}
            message = stream.get_final_message()
        add_cost(cost, message.usage)
        yield {'type': 'usage', 'cost': dict(cost), 'phase': 'research'}
        if message.stop_reason == 'refusal':
            yield {'type': 'error', 'message': 'The research request was declined.'}
            return
        research = ''.join(chunks).strip()

        yield {'type': 'status', 'step': 'structure',
               'message': 'Writing the battlecard'}
        card = _structure(client, competitor, product, preset, research, notes,
                          mode=mode, cost=cost)
        yield {'type': 'usage', 'cost': dict(cost), 'phase': 'card'}
        card = _merge_curated(card, competitor, product)
        card['meta'] = dict(card.get('meta', {}), **{
            'competitor': competitor,
            'ia_product': product,
            'solution': PRODUCT_SOLUTIONS.get(product, 'data_intelligence'),
            'depth': depth if depth in DEPTHS else DEFAULT_DEPTH,
            'distribution': 'internal',
            'audience': 'Sales and solution consulting',
        })
        yield {'type': 'card', 'card': card,
               'curated': bool(card.pop('_curated', False)),
               'research': research, 'cost': dict(cost),
               'economy': bool(economy)}
    except AIUnavailable as exc:
        yield {'type': 'error', 'message': str(exc)}
    except Exception as exc:  # surfaced to the UI rather than a blank failure
        log.exception('battlecard generation failed')
        yield {'type': 'error', 'message': '%s: %s' % (type(exc).__name__, exc)}


# ─── Chat assistant ─────────────────────────────────────────────────────────────

CHAT_SYSTEM = """You are the assistant inside the Impact Analytics battlecard builder.

You help a seller understand and improve the card they have open. Keep answers
short, three sentences where three will do. You know the battlecard sections, the
brand writing rules and the honesty rules above.

When the seller asks you to change the card, reply with the wording you propose
and name the section it belongs in. Do not claim you have applied it; the person
applies it.

When the seller asks about a competitor capability the card marks Unclear, say
plainly that it is unverified and give them the question to ask on the call. Never
fill the gap with a guess."""


def chat_stream(history: list, card: dict = None, product: str = ''):
    """Yield answer text for the builder's chat panel.

    A generator so the Flask route can stream it to the browser.
    """
    client = _client()
    competitor = (card or {}).get('meta', {}).get('competitor') or 'no competitor yet'

    system = _system_prompt(product, competitor)
    system.append({'type': 'text', 'text': CHAT_SYSTEM})
    if card:
        system.append({'type': 'text',
                       'text': 'The card currently open, as JSON:\n%s'
                               % json.dumps(_card_digest(card), indent=1)})

    messages = []
    for turn in history[-20:]:
        role = 'assistant' if turn.get('role') == 'assistant' else 'user'
        text = str(turn.get('content', ''))[:8000]
        if text:
            messages.append({'role': role, 'content': text})
    if not messages:
        return

    with client.messages.stream(
        model=MODEL,
        max_tokens=CHAT_MAX_TOKENS,
        system=system,
        thinking={'type': 'adaptive'},
        output_config={'effort': 'medium'},
        messages=messages,
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk


def _card_digest(card: dict) -> dict:
    """A compact view of the card, so the chat context stays small."""
    keep = ('meta', 'positioning', 'their_strengths', 'their_weaknesses',
            'our_advantages', 'objections', 'talk_track', 'proof_points')
    digest = {key: card.get(key) for key in keep if card.get(key)}
    comparison = card.get('comparison') or []
    digest['comparison'] = [
        {'capability': row.get('capability'), 'ia': row.get('ia'),
         'competitor': row.get('competitor')} for row in comparison[:20]
    ]
    return digest
