"""Render a battlecard as an Impact Analytics branded PDF.

A seller forwards a battlecard, so it has to stand on its own as a document:
the verdict first, the head to head chart next, then the plays. Layout is
computed here rather than reflowed from the web page, so the printed result
does not depend on whose browser produced it.

ReportLab's built-in fonts cover Latin-1 only, and a character outside it
renders as a solid black box rather than failing loudly. Every string is passed
through _safe() for that reason.
"""
from __future__ import annotations

import io
import os
from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer)

BLUE = colors.HexColor("#264CD7")
BLUE_DEEP = colors.HexColor("#16267A")
OFF_WHITE = colors.HexColor("#F4F4F6")
BLACK = colors.HexColor("#1C1B1B")
GREY = colors.HexColor("#6C6A66")
GREY_LINE = colors.HexColor("#E4E4E4")
ORANGE = colors.HexColor("#FF6F1C")
WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 17 * mm
CONTENT_W = PAGE_W - MARGIN * 2

# The header band is dark, so the logo variant made for a blue background is
# the one that belongs on it. The light-background asset carries an off-white
# field and would sit in a visible box. The band is painted in that asset's own
# blue so the two meet seamlessly rather than showing a seam.
LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "static", "brand", "logo-stacked-blue.png")
LOGO_FIELD = colors.Color(38 / 255, 75 / 255, 215 / 255)

# Characters that appear in generated copy but fall outside Latin-1, mapped to
# equivalents the built-in fonts can actually draw.
_REPLACEMENTS = {
    "→": "->", "←": "<-", "—": " - ", "–": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "•": "-", "…": "...", " ": " ", "≤": "<=",
    "≥": ">=", "×": "x", "✓": "y", "✗": "n",
}


def _safe(text: Any) -> str:
    """Make a string printable with the built-in fonts, and XML safe."""
    value = "" if text is None else str(text)
    for bad, good in _REPLACEMENTS.items():
        value = value.replace(bad, good)
    value = value.encode("latin-1", "replace").decode("latin-1")
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _num(value: Any, fallback: float = 0.0) -> float:
    """Coerce a score to a number.

    The card arrives from the browser, and a model can omit a dimension's score
    or return it as text. Neither is worth failing a download over, so an
    unusable value is treated as zero rather than raising mid-render.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _gap(row: dict) -> float:
    return _num(row.get("ia_score")) - _num(row.get("competitor_score"))


def _style(name: str, size: float, leading: float, colour=BLACK,
           bold: bool = False, space_after: float = 0, space_before: float = 0):
    return ParagraphStyle(
        name, fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size, leading=leading, textColor=colour,
        spaceAfter=space_after, spaceBefore=space_before, alignment=TA_LEFT)


S = {
    "h1": _style("h1", 19, 24, BLACK, True, 6),
    "label": _style("label", 8, 11, BLUE, True, 5, 12),
    "body": _style("body", 9.6, 14.5, BLACK, False, 5),
    "muted": _style("muted", 8.6, 13, GREY, False, 4),
    "bullet": _style("bullet", 9.6, 14.5, BLACK, False, 4),
    "playhead": _style("playhead", 9.8, 13, BLUE_DEEP, True, 2),
}


class AdvantageChart(Flowable):
    """Diverging bars centred on zero: who leads each dimension, by how much.

    The gap is the message, so the chart draws the gap itself rather than two
    bars a reader has to subtract. Every bar carries its value, which is also
    what keeps the lighter of the two hues readable in print.
    """

    ROW = 15.5
    NAME_W = 116
    VAL_W = 34

    def __init__(self, rows: list[dict], competitor: str, width: float):
        super().__init__()
        self.rows = rows
        self.competitor = competitor
        self.width = width
        self.height = self.ROW * len(rows) + 26

    def draw(self):
        c = self.canv
        track_x = self.NAME_W + 8
        track_w = self.width - self.NAME_W - self.VAL_W - 16
        mid = track_x + track_w / 2
        top = self.height - 16

        biggest = max((abs(_gap(r)) for r in self.rows), default=1) or 1

        c.setFont("Helvetica-Bold", 6.4)
        c.setFillColor(GREY)
        c.drawRightString(mid - 6, top + 7, _safe(self.competitor.upper() + " AHEAD"))
        c.drawString(mid + 6, top + 7, "IMPACT ANALYTICS AHEAD")

        for index, row in enumerate(self.rows):
            y = top - (index + 1) * self.ROW + 4
            gap = _gap(row)

            c.setFont("Helvetica", 7.4)
            c.setFillColor(BLACK)
            c.drawRightString(self.NAME_W, y + 1, _safe(row.get("label") or row.get("dimension"))[:34])

            c.setStrokeColor(GREY_LINE)
            c.setLineWidth(0.5)
            c.line(mid, y - 3, mid, y + 9)

            length = (abs(gap) / biggest) * (track_w / 2 - 6)
            if abs(gap) >= 0.05:
                c.setFillColor(BLUE if gap > 0 else ORANGE)
                x = mid if gap > 0 else mid - length
                c.roundRect(x, y - 1, max(length, 1.5), 7, 1.4,
                            stroke=0, fill=1)

            c.setFont("Helvetica-Bold", 7.4)
            c.setFillColor(BLUE if gap > 0.05 else (ORANGE if gap < -0.05 else GREY))
            c.drawRightString(self.width, y + 1,
                              f"{'+' if gap > 0 else ''}{gap:.1f}")


class ScoreHeader(Flowable):
    """The verdict block: both weighted scores and how many each side leads."""

    def __init__(self, card: dict, width: float):
        super().__init__()
        self.card = card
        self.width = width
        self.height = 52

    def draw(self):
        c = self.canv
        totals = self.card.get("totals") or {}
        rows = self.card.get("scorecard") or []
        wins = sum(1 for r in rows if _gap(r) > 0)
        figures = [
            ("Impact Analytics", f"{_num(totals.get('ia')):.1f}", BLUE),
            (_safe(self.card.get("competitor", "Competitor"))[:22],
             f"{_num(totals.get('competitor')):.1f}", ORANGE),
            ("Dimensions we lead", f"{wins}/{len(rows) or 10}", BLACK),
            ("Confidence", str(self.card.get("confidence", "medium")).title(), BLACK),
        ]
        box = (self.width - 3 * 8) / 4
        for index, (label, value, colour) in enumerate(figures):
            x = index * (box + 8)
            c.setFillColor(OFF_WHITE)
            c.roundRect(x, 0, box, self.height, 4, stroke=0, fill=1)
            c.setFillColor(colour)
            c.setFont("Helvetica-Bold", 17)
            c.drawString(x + 10, 22, value)
            c.setFillColor(GREY)
            c.setFont("Helvetica-Bold", 6.2)
            c.drawString(x + 10, 11, label.upper()[:26])


def _bullets(items, style=S["bullet"]) -> list:
    out = []
    for item in (items or [])[:8]:
        out.append(Paragraph(f"&bull;&nbsp;&nbsp;{_safe(item)}", style))
    return out


def _plays(items) -> list:
    out = []
    for play in (items or [])[:6]:
        if not isinstance(play, dict):
            continue
        out.append(Paragraph(_safe(play.get("play", "")), S["playhead"]))
        out.append(Paragraph(_safe(play.get("why_it_works", "")), S["muted"]))
    return out


def _pairs(items, key: str, value: str) -> list:
    out = []
    for pair in (items or [])[:6]:
        if not isinstance(pair, dict):
            continue
        out.append(Paragraph(f'"{_safe(pair.get(key, ""))}"', S["playhead"]))
        out.append(Paragraph(_safe(pair.get(value, "")), S["muted"]))
    return out


def _section(title: str, flowables: list) -> list:
    if not flowables:
        return []
    return [KeepTogether([Paragraph(title.upper(), S["label"])] + flowables[:2])] \
        + flowables[2:]


def build(card: dict[str, Any], meta: dict[str, Any] | None = None) -> io.BytesIO:
    """Render the battlecard. Returns a PDF ready to send."""
    meta = meta or {}
    competitor = card.get("competitor", "Competitor")
    buffer = io.BytesIO()

    def decorate(canvas, doc):
        canvas.saveState()
        # Header band, on the first page only, so later pages stay readable.
        if doc.page == 1:
            canvas.setFillColor(LOGO_FIELD)
            canvas.rect(0, PAGE_H - 34 * mm, PAGE_W, 34 * mm, stroke=0, fill=1)
            canvas.setStrokeColor(colors.Color(1, 1, 1, alpha=0.10))
            canvas.setLineWidth(0.4)
            for step in range(0, int(PAGE_W), 34):        # grid pattern, off-edge
                canvas.line(step, PAGE_H - 34 * mm, step, PAGE_H)
            if os.path.exists(LOGO):
                canvas.drawImage(LOGO, PAGE_W - MARGIN - 21 * mm, PAGE_H - 26 * mm,
                                 width=21 * mm, height=17.7 * mm,
                                 preserveAspectRatio=True, anchor="sw")
            canvas.setFillColor(WHITE)
            canvas.setFont("Helvetica-Bold", 7.4)
            canvas.drawString(MARGIN, PAGE_H - 16 * mm, "COMPETITIVE BATTLECARD")
            canvas.setFont("Helvetica-Bold", 18)
            canvas.drawString(MARGIN, PAGE_H - 24 * mm,
                              _safe(f"Impact Analytics vs {competitor}"))
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.78))
            canvas.drawString(MARGIN, PAGE_H - 30 * mm,
                              date.today().strftime("%d %B %Y"))
        # Confidentiality footer, on every page, per the brand rules.
        canvas.setFillColor(GREY)
        canvas.setFont("Helvetica", 6.6)
        canvas.drawString(MARGIN, 10 * mm,
                          "Confidential. Prepared by Impact Analytics. "
                          "Not for external distribution without permission.")
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(buffer, pagesize=A4,
                          leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=MARGIN, bottomMargin=MARGIN,
                          title=f"Impact Analytics vs {competitor}",
                          author="Impact Analytics")
    first = Frame(MARGIN, MARGIN + 6 * mm, CONTENT_W,
                  PAGE_H - 34 * mm - MARGIN - 6 * mm, id="first")
    later = Frame(MARGIN, MARGIN + 6 * mm, CONTENT_W,
                  PAGE_H - MARGIN * 2 - 6 * mm, id="later")
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first], onPage=decorate),
        PageTemplate(id="later", frames=[later], onPage=decorate),
    ])

    story: list = [Spacer(1, 6)]
    if card.get("verdict"):
        story.append(Paragraph(_safe(card["verdict"]), S["h1"]))
    story.append(Spacer(1, 6))
    story.append(ScoreHeader(card, CONTENT_W))
    story.append(Spacer(1, 14))

    rows = card.get("scorecard") or []
    if rows:
        ordered = sorted(rows, key=_gap, reverse=True)
        story.append(Paragraph("WHO LEADS EACH DIMENSION", S["label"]))
        story.append(AdvantageChart(ordered, competitor, CONTENT_W))
        story.append(Spacer(1, 8))

    story += _section("Who they are",
                      [Paragraph(_safe(card.get("who_they_are", "")), S["body"])]
                      if card.get("who_they_are") else [])
    story += _section("Where they win", _bullets(card.get("where_they_win")))
    story += _section("Where they are weak", _bullets(card.get("where_they_are_weak")))
    story += _section("How we win", _plays(card.get("how_we_win")))
    story += _section("Discovery questions", _bullets(card.get("discovery_questions")))
    story += _section("Objection handling",
                      _pairs(card.get("objection_handling"), "objection", "response"))
    story += _section("Landmines to avoid", _bullets(card.get("landmines")))
    if card.get("pricing_and_deployment"):
        story += _section("Pricing and deployment posture",
                          [Paragraph(_safe(card["pricing_and_deployment"]), S["body"])])
    story += _section("Proof points", _bullets(card.get("proof_points")))
    if card.get("threatened_products"):
        story += _section("IA products most exposed",
                          [Paragraph(_safe(", ".join(card["threatened_products"])),
                                     S["body"])])
    story += _section("Gaps in our intel", _bullets(card.get("intel_gaps")))

    sources = card.get("sources") or []
    web = [s.get("title") or s.get("url") for s in (card.get("research_sources") or [])]
    if sources or web:
        lines = []
        if sources:
            lines.append(Paragraph("Library: " + _safe(", ".join(sources)), S["muted"]))
        if web:
            lines.append(Paragraph("Research: " + _safe(", ".join(web)), S["muted"]))
        story += _section("Sources", lines)

    doc.build(story)
    buffer.seek(0)
    return buffer
