"""Make card text fit its box, and keep everything that does not fit.

The builder used to shrink text to a minimum size and then let it overflow, which
is how a generated card came out with paragraphs running off the bottom of their
panels and table rows off the bottom of the slide. Two things were wrong.

The measurement was short. PowerPoint's line spacing multiplies the font's own
line height, roughly 1.2 em for Inter Tight, so a paragraph written at 1.25
spacing needs about 1.5 em a line. The estimate assumed 1.22 em whatever the
spacing, so every paragraph came out about a quarter taller than planned.

And nothing happened when text was simply too long. A generated card writes
matrix notes of 400 characters and talk track blocks of 800, with the citation
for every claim inline. So this module does three jobs:

- `split_sources` lifts "Source: ..." sentences and ", per e-book page 19"
  clauses out of body copy. The slide reads as an argument, and the citations
  go to the speaker notes and to a short label where the slide has a proof slot.
- `fit_prose` finds the largest legible size a block fits at, and when it does
  not fit even at the floor, trims at a sentence boundary. The full text goes to
  the speaker notes, so a detail is moved, never lost.
- `fit_list` says how many list items fit, so a section paginates instead of
  shrinking a list into unreadable type.

Nothing here draws. The builder asks, then draws what it is told fits.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .brand import estimate_lines

EMU_PER_PT = 12700

# Inter Tight's natural line height, as a multiple of the size. PowerPoint's
# line spacing multiplies this, it does not replace it.
NATURAL_LINE = 1.21

# The width estimate works from an average glyph width and real text wraps a
# little earlier, so measuring against a slightly narrower column errs long. A
# box with spare space is fine; a box that overflows is the bug being fixed.
WIDTH_SAFETY = 0.92

# Bold display type runs wider than the regular weight the glyph average was
# taken from. Found when a bold four line question landed on its own label.
BOLD_WIDTH = 0.9

# The bullet hanging indent from brand.apply_bullet.
BULLET_INDENT_EMU = int(0.16 * 914400)

ELLIPSIS = '…'


# ─── Measuring ──────────────────────────────────────────────────────────────────

def line_pitch(pt: float, spacing: float) -> float:
    """The distance between baselines, in EMU."""
    return pt * NATURAL_LINE * spacing * EMU_PER_PT


def measure(text: str, width_emu: int, pt: float, spacing: float = 1.2,
            bullet: bool = False, bold: bool = False) -> int:
    """How tall `text` renders, in EMU, erring on the tall side."""
    if not text:
        return 0
    usable = int(width_emu * WIDTH_SAFETY * (BOLD_WIDTH if bold else 1.0)) \
        - (BULLET_INDENT_EMU if bullet else 0)
    lines = estimate_lines(text, max(usable, 1), pt)
    return int(lines * line_pitch(pt, spacing))


def measure_list(items, width_emu: int, pt: float, spacing: float = 1.2,
                 gap_pt: float = 4.0, bullet: bool = True) -> int:
    items = [item for item in items if item]
    if not items:
        return 0
    body = sum(measure(item, width_emu, pt, spacing, bullet) for item in items)
    return body + int(gap_pt * EMU_PER_PT) * (len(items) - 1)


# ─── Sentences ──────────────────────────────────────────────────────────────────

# A sentence ends at a full stop, question or exclamation mark followed by a
# space and a capital, or the end of the text. A full stop inside "1.2", "p. 4"
# or "AssortSmart_Eng.pdf" is not followed by space and a capital, so it holds.
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"“(])')


def sentences(text: str) -> list:
    text = (text or '').strip()
    if not text:
        return []
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


# ─── Sources out of body copy ───────────────────────────────────────────────────

# "Source: X." or "Sources: A and B." up to the end of that sentence.
_SOURCE_SENTENCE = re.compile(
    r'\s*\bSources?:\s*(?P<src>.+?)(?:\.(?=\s+[A-Z]|\s*$)|$)', re.S)

# ", per Assortment_Planning_E-book.pdf pages 15 and 16" and ", per e-book page 19".
_PER_CLAUSE = re.compile(
    r',?\s+per\s+(?P<src>(?:the\s+)?[\w\-]+(?:\.(?:pdf|docx|pptx|xlsx))?'
    r'(?:\s+(?:e-book|ebook|deck|document))?'
    r'(?:,?\s+(?:pages?|section|slide)\s+\d+(?:\.\d+)*'
    r'(?:\s*(?:,|and|to)\s*(?:pages?\s+)?\d+(?:\.\d+)*)*)?)'
    r'(?=[\s,.;:)]|$)',
    re.I)

# A per clause only counts when it names a document, so ordinary prose such as
# "per store" or "per SKU" is never touched.
_DOCUMENT_HINT = re.compile(r'\.(?:pdf|docx|pptx|xlsx)\b|e-?book|\bpages?\s+\d|\bsection\s+\d',
                            re.I)

_BARE_URL = re.compile(r'\s*\(?https?://[^\s)]+\)?')


def split_sources(text: str):
    """Return (the text without its citations, the citations it carried)."""
    if not text:
        return '', []
    found = []

    def take_sentence(match):
        found.append(match.group('src').strip().rstrip('.'))
        return ''

    def take_clause(match):
        source = match.group('src').strip()
        if not _DOCUMENT_HINT.search(source):
            return match.group(0)
        found.append(source.rstrip('.,'))
        return ''

    def take_url(match):
        found.append(match.group(0).strip(' ()'))
        return ''

    clean = _SOURCE_SENTENCE.sub(take_sentence, text)
    clean = _PER_CLAUSE.sub(take_clause, clean)
    clean = _BARE_URL.sub(take_url, clean)
    clean = re.sub(r'\s+([.,;:])', r'\1', clean)
    clean = re.sub(r'([.,;:])\1+', r'\1', clean)
    clean = re.sub(r'\s{2,}', ' ', clean).strip()
    return clean, found


# ─── Short citation labels ──────────────────────────────────────────────────────

_SPLIT_SOURCES = re.compile(
    r'\s*(?:;|,\s+(?=https?://)|\s+and\s+(?=https?://|[\w\-]+\.(?:pdf|docx|pptx|xlsx)\b))\s*',
    re.I)
_PAGES = re.compile(r'\bpages?\s+([\d\s,andto]+)', re.I)
_SECTION = re.compile(r'\bsection\s+([\d.]+)', re.I)


def _page_label(text: str) -> str:
    numbers = []
    for chunk in _PAGES.findall(text):
        numbers.extend(int(n) for n in re.findall(r'\d+', chunk))
    numbers = sorted(set(numbers))
    if not numbers:
        return ''
    if len(numbers) == 1:
        return 'p. %d' % numbers[0]
    if numbers == list(range(numbers[0], numbers[-1] + 1)):
        return 'pp. %d to %d' % (numbers[0], numbers[-1])
    return 'pp. %s' % ', '.join(str(n) for n in numbers[:4])


def _file_label(text: str) -> str:
    match = re.search(r'([\w\-]+)\.(pdf|docx|pptx|xlsx)\b', text, re.I)
    if not match:
        return ''
    name = match.group(1).replace('_', ' ').replace('-', ' ').strip()
    return re.sub(r'\s{2,}', ' ', name)


def cite(source: str):
    """One citation as (label, url or None), short enough for a proof slot."""
    source = (source or '').strip().rstrip('.')
    if not source:
        return None
    if source.lower().startswith('http'):
        host = urlsplit(source).hostname or source
        return (host[4:] if host.startswith('www.') else host), source
    name = _file_label(source)
    if name:
        where = _page_label(source)
        section = _SECTION.search(source)
        if section and not where:
            where = 'sec. %s' % section.group(1).rstrip('.')
        return ('%s, %s' % (name, where) if where else name), None
    # A named source with no file: "Preqin asset profile and Crustdata profile".
    return re.sub(r',?\s*internal only\.?$', '', source, flags=re.I)[:60], None


def cites(text: str) -> list:
    """Every citation in a proof string, deduplicated, in order.

    A proof field can carry several sources and a trailing sentence, as in
    "https://... Brand reach figures from IA_with_o9_Solutions.docx, section
    1.6", so it is split on sentences first, and a URL is cut at its first space
    so the words after it never become part of the link.
    """
    out, seen = [], set()
    parts = []
    for sentence in sentences(text or ''):
        parts.extend(_SPLIT_SOURCES.split(sentence))
    for part in parts:
        part = re.sub(r',?\s*internal only\.?$', '', part.strip(), flags=re.I)
        url = re.match(r'https?://\S+', part)
        if url:
            part = url.group(0).rstrip('.,;)')
        label = cite(part)
        if label and label[0].lower() not in seen:
            seen.add(label[0].lower())
            out.append(label)
    return out


# ─── Fitting ────────────────────────────────────────────────────────────────────

def _sizes(max_pt: float, min_pt: float, step: float = 0.5):
    size = max_pt
    while size >= min_pt - 1e-6:
        yield round(size, 1)
        size -= step


def trim_to(text: str, width_emu: int, height_emu: int, pt: float,
            spacing: float = 1.2, bullet: bool = False, bold: bool = False) -> str:
    """The longest run of whole sentences that fits. Never a half sentence,
    unless the first sentence alone is too long, and then a clean word break."""
    kept = ''
    for sentence in sentences(text):
        candidate = (kept + ' ' + sentence).strip()
        if measure(candidate, width_emu, pt, spacing, bullet, bold) <= height_emu:
            kept = candidate
        else:
            break
    if kept:
        return kept
    words = (text or '').split()
    kept = ''
    for word in words:
        candidate = (kept + ' ' + word).strip()
        if measure(candidate + ELLIPSIS, width_emu, pt, spacing, bullet, bold) <= height_emu:
            kept = candidate
        else:
            break
    return (kept.rstrip('.,;:') + ELLIPSIS) if kept else ''


def fit_prose(text: str, width_emu: int, height_emu: int, max_pt: float,
              min_pt: float, spacing: float = 1.2, bold: bool = False):
    """(size, text to draw, whether anything was held back).

    When the block has to be trimmed, the trimmed text is then drawn at the
    largest size it fits, so a box does not end with its last sentence small
    and a band of empty space beneath it.
    """
    text = (text or '').strip()
    if not text:
        return max_pt, '', False
    for pt in _sizes(max_pt, min_pt):
        if measure(text, width_emu, pt, spacing, bold=bold) <= height_emu:
            return pt, text, False
    shown = trim_to(text, width_emu, height_emu, min_pt, spacing, bold=bold)
    for pt in _sizes(max_pt, min_pt):
        if measure(shown, width_emu, pt, spacing, bold=bold) <= height_emu:
            return pt, shown, shown != text
    return min_pt, shown, shown != text


def fit_list(items, width_emu: int, height_emu: int, max_pt: float, min_pt: float,
             spacing: float = 1.2, gap_pt: float = 4.0, bullet: bool = True):
    """(size, how many items fit). Every item fits at `min_pt` or the caller
    has trimmed it first, so the answer is always at least one."""
    items = [item for item in items if item]
    if not items:
        return max_pt, 0
    for pt in _sizes(max_pt, min_pt):
        if measure_list(items, width_emu, pt, spacing, gap_pt, bullet) <= height_emu:
            return pt, len(items)
    count = 0
    for index in range(1, len(items) + 1):
        if measure_list(items[:index], width_emu, min_pt, spacing, gap_pt,
                        bullet) <= height_emu:
            count = index
        else:
            break
    return min_pt, max(1, count)


def balance(total: int, per_page: int) -> list:
    """Split `total` into pages as evenly as possible, never a lone orphan.

    Ten items at three a page is 3, 3, 2, 2 rather than 3, 3, 3, 1, which is how
    a slide ended up holding a single card stretched across the whole width.
    """
    if total <= 0:
        return []
    pages = -(-total // max(1, per_page))
    base, extra = divmod(total, pages)
    return [base + (1 if index < extra else 0) for index in range(pages)]
