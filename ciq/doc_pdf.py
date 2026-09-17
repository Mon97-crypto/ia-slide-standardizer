"""Build a PDF for a library entry whose original document is not held.

Every entry needs a file someone can open and send on. Most now keep the
document they were created from; the ones added before files were kept, along
with notes and links that could not be fetched, have only the text that was
extracted at the time. Refusing those would leave part of the library
unopenable, so this renders what does exist as a real document.

It says plainly, on the page, that it was built from extracted text rather
than being the original, because it will be forwarded to people who never saw
the entry it came from.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

from . import pdf_fonts
from .config import CATEGORIES

BLUE = colors.HexColor("#264CD7")
BLACK = colors.HexColor("#1C1B1B")
GREY = colors.HexColor("#6C6A66")
OFF_WHITE = colors.HexColor("#F4F4F6")
FIELD = colors.Color(38 / 255, 75 / 255, 215 / 255)

PAGE_W, PAGE_H = A4
MARGIN = 17 * mm
CONTENT_W = PAGE_W - MARGIN * 2
BAND_H = 30 * mm

# Long enough to be worth reading, short enough that one entry cannot produce
# a hundred page download.
MAX_CHARS = 400_000


def _notice(entry: dict) -> str:
    """Why this file is not the original, in the terms that actually apply."""
    if (entry.get("source_kind") or "") == "note":
        return ("This entry is a note written into the library rather than an "
                "uploaded document. The text below is the note itself.")
    if entry.get("file_name"):
        return (f"The original file, {entry['file_name']}, is not held for "
                "this entry - it was added before the library kept uploads. "
                "The text below is what was extracted from it at the time, "
                "and is what searches and analyses of this entry are built "
                "on. Use Attach file on the entry to put the original back.")
    return ("No original document is held for this entry. The text below is "
            "everything the library holds for it.")


def _paragraphs(text: str) -> list[str]:
    """Split extracted text back into something readable.

    Extraction flattens a document to plain text, so blank lines are the only
    paragraph boundary left. A single unbroken block is split on sentence ends
    instead, because one thirty thousand character paragraph is unreadable and
    ReportLab has to lay it out as one unbreakable flowable.
    """
    text = (text or "").strip()
    if not text:
        return []
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    out: list[str] = []
    for block in blocks:
        if len(block) <= 1500:
            out.append(block)
            continue
        sentences, current = re.split(r"(?<=[.!?])\s+", block), ""
        for sentence in sentences:
            if len(current) + len(sentence) > 1200 and current:
                out.append(current.strip())
                current = ""
            current += sentence + " "
        if current.strip():
            out.append(current.strip())
    return out


def build(entry: dict) -> io.BytesIO:
    """Render the entry. Returns a PDF ready to send."""
    fonts = pdf_fonts.load()
    clean = fonts.clean

    def style(name, size, leading, colour=BLACK, font=None, **kwargs):
        return ParagraphStyle(name, fontName=font or fonts.regular,
                              fontSize=size, leading=leading, textColor=colour,
                              alignment=TA_LEFT, **kwargs)

    body = style("body", 9.8, 15, BLACK, spaceAfter=8)
    note = style("note", 8.4, 12.4, GREY)
    label = style("label", 7.6, 11, BLUE, fonts.bold, spaceAfter=4)
    fact = style("fact", 8.6, 12.6, GREY)

    title = entry.get("title") or "Untitled entry"
    competitor = entry.get("competitor") or ""
    category = CATEGORIES.get(entry.get("category") or "", "File")
    stamp = datetime.now(timezone.utc).strftime("%d %B %Y at %H:%M UTC")

    def decorate(canvas, doc):
        canvas.saveState()
        if doc.page == 1:
            canvas.setFillColor(FIELD)
            canvas.rect(0, PAGE_H - BAND_H, PAGE_W, BAND_H, stroke=0, fill=1)
            canvas.setStrokeColor(colors.Color(1, 1, 1, alpha=0.10))
            canvas.setLineWidth(0.4)
            for step in range(0, int(PAGE_W), 34):
                canvas.line(step, PAGE_H - BAND_H, step, PAGE_H)
            canvas.setFillColor(colors.white)
            canvas.setFont(fonts.bold, 7.2)
            canvas.drawString(MARGIN, PAGE_H - 12 * mm,
                              clean(category.upper()))
            canvas.setFont(fonts.bold, 15)
            canvas.drawString(MARGIN, PAGE_H - 19 * mm,
                              _fit(canvas, title, fonts.bold, 15, CONTENT_W,
                                   clean))
            if competitor:
                canvas.setFont(fonts.regular, 7.8)
                canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.80))
                canvas.drawString(MARGIN, PAGE_H - 24.5 * mm, clean(competitor))
        canvas.setFillColor(GREY)
        canvas.setFont(fonts.regular, 6.6)
        canvas.drawString(MARGIN, 10 * mm, clean(
            "Impact Analytics competitor intelligence. Confidential. "
            f"Exported {stamp}."))
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN,
                          rightMargin=MARGIN, topMargin=MARGIN,
                          bottomMargin=MARGIN, title=title[:120],
                          author="Impact Analytics")
    doc.addPageTemplates([
        PageTemplate(id="first", onPage=decorate, frames=[
            Frame(MARGIN, MARGIN + 6 * mm, CONTENT_W,
                  PAGE_H - BAND_H - MARGIN - 6 * mm, id="f")]),
        PageTemplate(id="later", onPage=decorate, frames=[
            Frame(MARGIN, MARGIN + 6 * mm, CONTENT_W,
                  PAGE_H - MARGIN * 2 - 6 * mm, id="l")]),
    ])

    story: list = [Spacer(1, 8),
                   _panel(clean(_notice(entry)), note), Spacer(1, 14)]

    facts = []
    if entry.get("created_at"):
        facts.append(f"Added {entry['created_at'][:10]}")
    if entry.get("file_name"):
        facts.append(entry["file_name"])
    if entry.get("content_chars"):
        facts.append(f"{entry['content_chars']:,} characters indexed")
    if facts:
        story.append(Paragraph(clean(" · ".join(facts)), fact))
        story.append(Spacer(1, 12))

    if entry.get("note"):
        story.append(Paragraph("NOTE", label))
        story.append(Paragraph(clean(entry["note"]), body))
        story.append(Spacer(1, 6))

    text = (entry.get("content") or "")[:MAX_CHARS]
    paragraphs = _paragraphs(text)
    if paragraphs:
        story.append(Paragraph("DOCUMENT TEXT", label))
        for paragraph in paragraphs:
            story.append(Paragraph(clean(paragraph), body))
    elif not entry.get("note"):
        story.append(Paragraph(clean(
            "No text was extracted for this entry."), body))
    if len(entry.get("content") or "") > MAX_CHARS:
        story.append(Spacer(1, 6))
        story.append(Paragraph(clean(
            "The text continued past the export limit and was cut off here."),
            fact))

    doc.build(story)
    buffer.seek(0)
    return buffer


def _panel(text: str, style):
    table = Table([[Paragraph(text, style)]], colWidths=[CONTENT_W])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), OFF_WHITE),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, BLUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return table


def _fit(canvas, text, font, size, width, clean):
    value = clean(text)
    if canvas.stringWidth(value, font, size) <= width:
        return value
    while value and canvas.stringWidth(value + "...", font, size) > width:
        value = value[:-1]
    return value + "..."


def filename_for(entry: dict) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-",
                  entry.get("title") or "").strip("-") or "entry"
    return base[:70] + ".pdf"
