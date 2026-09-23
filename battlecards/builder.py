"""Slide builders for the Impact Analytics competitive battlecard.

Every slide is drawn on a blank layout with explicit geometry, explicit fills and
explicit run level fonts. Nothing inherits from a theme, nothing relies on
PowerPoint autofit, and nothing uses an effect Google Slides drops on import. The
result opens the same way in PowerPoint, Keynote and Google Slides.
"""

from __future__ import annotations

import math
import re
from datetime import date

from lxml import etree

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from . import brand, typeset
from .brand import (ACCENT_ORANGE, BLACK, GRAY_1, GRAY_2, GRAY_3, IMPACT_BLUE,
                    OFF_WHITE, SECONDARY_FONT, SOLUTION_LABELS, WHITE, Theme,
                    add_picture, add_rect, add_soft_shadow, add_textbox,
                    fit_block_size, fit_size, logo_for_background, mix,
                    prepare_text_frame, set_run_font, text_height,
                    write_paragraph, write_two_tone)
from .patterns import grid_overlay
from .schema import RATING_LABELS, SECTION_LABELS

# The house canvas, measured from the IA template: 10 x 5.625in.
SLIDE_W = Emu(9144000)    # exactly 10.000in
SLIDE_H = Emu(5143500)    # exactly 5.625in
MARGIN = Inches(0.3)
CONTENT_W = SLIDE_W - 2 * MARGIN

# Header block. The house template puts the title at left 0.14in, top 0.02in to
# 0.22in, and separates it from the body with whitespace, never a rule.
KICKER_TOP = Inches(0.18)
TITLE_TOP = Inches(0.36)
TITLE_H = Inches(0.52)
BODY_TOP = Inches(1.0)
BODY_BOTTOM = Inches(5.08)
BODY_H = BODY_BOTTOM - BODY_TOP
FOOTER_TEXT_Y = Inches(5.19)   # matches the template footer position exactly

GUTTER = Inches(0.16)
PAD = Inches(0.16)
# Logo sits top right, clear of the title, so titles get the remaining width.
TITLE_W = CONTENT_W - Inches(1.25)

RATING_COLORS = {
    'strong': IMPACT_BLUE,
    'partial': BLACK,
    'none': ACCENT_ORANGE,   # the only orange in the deck, which keeps it an accent
    'unknown': GRAY_3,
}


def chunk(items, size):
    size = max(1, size)
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]


class BattlecardDeck:
    """Turns a normalised battlecard into a Presentation."""

    def __init__(self, card: dict):
        self.card = card
        self.meta = card['meta']
        options = card.get('options', {})
        solution = self.meta.get('solution') or brand.solution_for_product(self.meta.get('ia_product', ''))
        self.solution = solution if solution in SOLUTION_LABELS else brand.DEFAULT_SOLUTION
        self.theme = Theme.for_solution(self.solution, options.get('serif_headings', False))
        self.include_notes = options.get('include_notes', True)
        self.sections = options.get('sections') or list(SECTION_LABELS)
        # The house stat card tints its inner panel with the Data & Intelligence
        # blue. Solution themed cards tint with their own accent instead, which
        # keeps one solution colour per composition.
        self.stat_tint = mix(self.theme.accent, WHITE, 0.45)
        self.prs = Presentation()
        self.prs.slide_width = SLIDE_W
        self.prs.slide_height = SLIDE_H
        self._apply_theme_fonts()
        self.page = 0
        # What a slide could not show: text held back by the fitter, and the
        # citations lifted out of body copy. It goes to that slide's speaker
        # notes, so a detail moves off the face of the slide, never out of the deck.
        self._held = []
        self._sources = []

    # ── presentation level ─────────────────────────────────────────────────────

    def _apply_theme_fonts(self):
        """Name the brand fonts and link colour in the theme as well as on every run.

        Runs already carry their own typeface, so rendering never depends on this.
        Setting the theme too means a user who edits the deck in Google Slides or
        PowerPoint gets Inter Tight on any new text box.
        """
        theme_rel = ('http://schemas.openxmlformats.org/officeDocument/2006/'
                     'relationships/theme')
        try:
            part = self.prs.slide_masters[0].part.part_related_by(theme_rel)
            root = etree.fromstring(part.blob)
        except Exception:
            return
        # Links take the theme's hyperlink colour whatever the run says, so the
        # theme has to name Impact Blue, or a proof label renders in the office
        # default blue, and a visited one in gray, beside brand blue text.
        for tag in ('a:hlink', 'a:folHlink'):
            node = root.find('.//' + qn('a:clrScheme') + '/' + qn(tag))
            if node is not None:
                for child in list(node):
                    node.remove(child)
                etree.SubElement(node, qn('a:srgbClr')).set('val', '264CD7')
        font_scheme = root.find('.//' + qn('a:fontScheme'))
        if font_scheme is not None:
            self._theme_fonts(font_scheme)
        try:
            part._blob = etree.tostring(root, xml_declaration=True,
                                        encoding='UTF-8', standalone=True)
        except Exception:
            return

    def _theme_fonts(self, font_scheme):
        for tag, name in (('a:majorFont', self.theme.heading_font),
                          ('a:minorFont', self.theme.body_font)):
            node = font_scheme.find(qn(tag))
            if node is None:
                continue
            latin = node.find(qn('a:latin'))
            if latin is not None:
                latin.set('typeface', name)

    def build(self) -> Presentation:
        builders = {
            'cover': self.slide_cover,
            'how_to_use': self.slide_how_to_use,
            'snapshot': self.slide_snapshot,
            'positioning': self.slide_positioning,
            'strengths_weaknesses': self.slide_strengths_weaknesses,
            'why_we_win': self.slide_why_we_win,
            'comparison': self.slide_comparison,
            'objections': self.slide_objections,
            'landmines': self.slide_landmines,
            'discovery': self.slide_discovery,
            'proof_points': self.slide_proof_points,
            'talk_track': self.slide_talk_track,
            'dos_donts': self.slide_dos_donts,
            'pricing': self.slide_pricing,
            'next_steps': self.slide_next_steps,
            'one_pager': self.slide_one_pager,
        }
        for name in self.sections:
            builder = builders.get(name)
            if builder:
                builder()
        return self.prs

    # ── slide chrome ───────────────────────────────────────────────────────────

    def _slide(self, dark=False, patterned=False):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        bg = IMPACT_BLUE if dark else OFF_WHITE
        add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, fill=bg)
        if patterned:
            overlay = grid_overlay()
            if overlay:
                add_picture(slide, overlay, 0, 0, SLIDE_W, SLIDE_H)
        return slide

    def _header(self, slide, title, kicker=None, dark=False):
        """Draw the house header: small kicker, two tone title, no rule.

        `title` is either a plain string or a (lead, emphasis) pair. The pair
        renders the template's signature split, Black then Impact Blue.
        """
        ink = WHITE if dark else BLACK
        kicker_color = mix(WHITE, IMPACT_BLUE, 0.35) if dark else IMPACT_BLUE
        kicker_text = kicker if kicker is not None else self._default_kicker()

        if kicker_text:
            box = add_textbox(slide, MARGIN, KICKER_TOP, TITLE_W, Inches(0.16))
            write_paragraph(box.text_frame, kicker_text.upper(), Pt(8), bold=True,
                            color=kicker_color, font=self.theme.body_font,
                            space_after=0, line_spacing=1.0, first=True)

        lead, emphasis = title if isinstance(title, tuple) else (title, '')
        full = (lead or '') + (emphasis or '')
        size = fit_size(full, int(TITLE_W), int(TITLE_H), 24, 14)
        title_box = add_textbox(slide, MARGIN, TITLE_TOP, TITLE_W, TITLE_H)
        write_two_tone(title_box.text_frame, lead, emphasis, size,
                       lead_color=ink,
                       emphasis_color=WHITE if dark else IMPACT_BLUE,
                       font=self.theme.heading_font)
        self._logo(slide, dark)

    def _logo(self, slide, dark=False, height=Inches(0.3)):
        path = logo_for_background(dark)
        if not path:
            return
        width = int(height / brand.LOGO_ASPECT)
        add_picture(slide, path, SLIDE_W - MARGIN - width, KICKER_TOP - Inches(0.02),
                    width, height)

    def _footer(self, slide, dark=False):
        """Write the house footer: two lines of Lato at the template position."""
        self.page += 1
        ink = mix(WHITE, IMPACT_BLUE, 0.45) if dark else GRAY_3
        box = add_textbox(slide, MARGIN, FOOTER_TEXT_Y, Inches(3.3), Inches(0.3))
        tf = box.text_frame
        write_paragraph(tf, 'Impact Analytics', Pt(5), color=ink,
                        font=SECONDARY_FONT, space_after=0, line_spacing=1.0,
                        first=True)
        write_paragraph(tf, '%s %s' % (self._footer_year(), self.meta['confidentiality']),
                        Pt(5), color=ink, font=SECONDARY_FONT, space_after=0,
                        line_spacing=1.0)
        page_box = add_textbox(slide, SLIDE_W - MARGIN - Inches(0.8), FOOTER_TEXT_Y,
                               Inches(0.8), Inches(0.3))
        write_paragraph(page_box.text_frame, str(self.page), Pt(6), color=ink,
                        font=SECONDARY_FONT, align=PP_ALIGN.RIGHT,
                        space_after=0, line_spacing=1.0, first=True)

    def _footer_year(self) -> str:
        """Take the year from the card date, falling back to the current year."""
        match = re.search(r'(20\d{2})', self.meta.get('date', '') or '')
        return match.group(1) if match else str(date.today().year)

    def _default_kicker(self, counter=None):
        text = '%s battlecard  ·  %s' % (
            SOLUTION_LABELS.get(self.solution, ''), self.meta['competitor'])
        if counter and counter[1] > 1:
            text += '  ·  %d of %d' % counter
        return text

    def _notes(self, slide, text):
        """Write the coaching line, then everything the slide held back."""
        parts = [text] if text else []
        if self._held:
            parts.append('IN FULL\n' + '\n\n'.join(
                '%s: %s' % (label, body) if label else body
                for label, body in self._held))
        if self._sources:
            seen, unique = set(), []
            for source in self._sources:
                if source.lower() not in seen:
                    seen.add(source.lower())
                    unique.append(source)
            parts.append('SOURCES\n' + '\n'.join('- ' + source for source in unique))
        self._held, self._sources = [], []
        if self.include_notes and parts:
            slide.notes_slide.notes_text_frame.text = '\n\n'.join(parts)

    def _page(self, title, kicker=None, dark=False, patterned=False, counter=None):
        self._held, self._sources = [], []
        slide = self._slide(dark=dark, patterned=patterned)
        if kicker is None and counter:
            kicker = self._default_kicker(counter)
        self._header(slide, title, kicker, dark=dark)
        self._footer(slide, dark=dark)
        return slide

    # ── reusable blocks ────────────────────────────────────────────────────────
    # Nothing in here draws text that has not been measured first. A block that
    # does not fit at its floor size is trimmed at a sentence boundary and the
    # whole of it goes to the speaker notes, so the face of the slide stays clean
    # and the detail stays in the deck.

    LABEL_H = Inches(0.2)

    def _panel(self, slide, left, top, width, height, fill=None, border=None,
               shadow=True, accent=None, accent_height=None):
        """Draw a house card: white, rounded, soft shadow, no border, no stripe."""
        panel = add_rect(slide, left, top, width, height,
                         fill=fill or WHITE, line=border,
                         line_width=Pt(0.75), rounded=True)
        if shadow:
            add_soft_shadow(panel)
        return panel

    def _panel_label(self, slide, left, top, width, text, color=None, size=Pt(7.5)):
        box = add_textbox(slide, left, top, width, Inches(0.18))
        write_paragraph(box.text_frame, text.upper(), size, bold=True,
                        color=color or IMPACT_BLUE, font=self.theme.body_font,
                        space_after=0, line_spacing=1.0, first=True)
        return box

    def _pill(self, slide, left, top, avail_w, text, width=None, fill=None,
              size=Pt(10)):
        """The house blue pill, floated over the top edge of a card."""
        pill_w = width or avail_w
        pill_left = left + (avail_w - pill_w) / 2
        shape = add_rect(slide, pill_left, top, pill_w, Inches(0.26),
                         fill=fill or IMPACT_BLUE, rounded=True, radius=45000)
        tf = prepare_text_frame(shape, margin=Inches(0.06), anchor=MSO_ANCHOR.MIDDLE)
        write_paragraph(tf, text, size, bold=True, color=WHITE,
                        font=self.theme.body_font, align=PP_ALIGN.CENTER,
                        space_after=0, line_spacing=1.0, first=True)
        return shape

    # ── text that always fits ──────────────────────────────────────────────────

    def _hold(self, label, text):
        if text:
            self._held.append((label, text))

    def _clean(self, text):
        """Body copy without its inline citations, which go to the notes."""
        clean, found = typeset.split_sources(text or '')
        self._sources.extend(found)
        return clean

    def _prose(self, slide, left, top, width, height, text, *, max_pt=10.5,
               min_pt=8.5, color=BLACK, bold=False, font=None,
               align=PP_ALIGN.LEFT, spacing=1.2, italic=False, label='',
               clean=True):
        """Draw a block that fits its box, and return the height it used."""
        text = self._clean(text) if clean else (text or '').strip()
        if not text or height <= 0:
            return 0
        pt, shown, trimmed = typeset.fit_prose(text, int(width), int(height),
                                               max_pt, min_pt, spacing, bold=bold)
        if trimmed:
            self._hold(label, text)
        if not shown:
            return 0
        used = min(int(height), typeset.measure(shown, int(width), pt, spacing,
                                                bold=bold))
        box = add_textbox(slide, left, top, width, max(used, int(Inches(0.12))))
        write_paragraph(box.text_frame, shown, Pt(pt), bold=bold, color=color,
                        font=font or self.theme.body_font, align=align,
                        space_after=0, line_spacing=spacing, first=True,
                        italic=italic)
        return used

    def _paragraph_block(self, slide, left, top, width, height, text, *,
                         max_pt=12.0, min_pt=8.0, color=BLACK, bold=False,
                         align=PP_ALIGN.LEFT, font=None, label=''):
        return self._prose(slide, left, top, width, height, text, max_pt=max_pt,
                           min_pt=min_pt, color=color, bold=bold, align=align,
                           font=font, label=label)

    def _prep(self, items, width, min_pt=8.5, max_lines=4, label=''):
        """Clean list items, and cap any single item at a few lines.

        Each entry carries its own citations and full text, so whichever page it
        lands on gets its notes, not the page that happened to be open.
        """
        cap = int(typeset.line_pitch(min_pt, 1.2) * max_lines)
        out = []
        for item in items or []:
            clean, found = typeset.split_sources(item or '')
            if not clean:
                continue
            full = ''
            if typeset.measure(clean, int(width), min_pt, 1.2, bullet=True) > cap:
                full = clean
                clean = typeset.trim_to(clean, int(width), cap, min_pt, 1.2, bullet=True)
            out.append({'text': clean, 'full': full, 'sources': found, 'label': label})
        return out

    def _register(self, entry):
        self._sources.extend(entry.get('sources') or [])
        if entry.get('full'):
            self._hold(entry.get('label', ''), entry['full'])

    def _split(self, entries, width, height, max_pt=10.5, min_pt=8.5, pages=0):
        """Pages of entries, spread evenly rather than filled then spilled.

        Filling decides how many pages the list needs. The entries are then
        shared out evenly across that many, or across `pages` when a paired
        column needs more, so the last page is never one stray bullet. If an even
        page would not fit, filling order stands.
        """
        greedy, rest = [], list(entries)
        while rest:
            _, count = typeset.fit_list([e['text'] for e in rest], int(width),
                                        int(height), max_pt, min_pt)
            greedy.append(rest[:count])
            rest = rest[count:]
        if not greedy:
            return [[]]
        target = max(len(greedy), pages)
        if target == 1 or len(entries) < target:
            return greedy
        even, start = [], 0
        for size in typeset.balance(len(entries), -(-len(entries) // target)):
            even.append(entries[start:start + size])
            start += size
        for page in even:
            _, count = typeset.fit_list([e['text'] for e in page], int(width),
                                        int(height), max_pt, min_pt)
            if count < len(page):
                return greedy
        return even

    def _bullets(self, slide, left, top, width, height, items, *, max_pt=10.5,
                 min_pt=8.5, color=BLACK, bullet_color=None, bullet='•', label=''):
        """Draw the items that fit and return the ones that did not."""
        entries = items if items and isinstance(items[0], dict) else \
            self._prep(items, width, min_pt, label=label)
        if not entries:
            return []
        pt, count = typeset.fit_list([e['text'] for e in entries], int(width),
                                     int(height), max_pt, min_pt)
        shown = entries[:count]
        box = add_textbox(slide, left, top, width, height)
        tf = box.text_frame
        for index, entry in enumerate(shown):
            self._register(entry)
            write_paragraph(tf, entry['text'], Pt(pt), color=color,
                            font=self.theme.body_font, bullet=bullet, space_after=4,
                            line_spacing=1.2, first=index == 0)
            if bullet_color is not None:
                brand.apply_bullet(tf.paragraphs[index], bullet, bullet_color)
        return entries[count:]

    def _group_pt(self, blocks, max_pt, min_pt, bold=False):
        """One size for sibling blocks: the largest at which every one fits.

        Cards side by side at different sizes read as a draft even when nothing
        overflows. `blocks` is a list of (text, width, height).
        """
        best = max_pt
        for text, width, height in blocks:
            text = typeset.split_sources(text or '')[0]
            if not text:
                continue
            size = min_pt
            for pt in typeset._sizes(max_pt, min_pt):
                if typeset.measure(text, int(width), pt, bold=bold) <= height:
                    size = pt
                    break
            best = min(best, size)
        return best

    def _stack(self, slide, left, top, width, bottom, blocks, gap=Inches(0.09)):
        """Place labelled blocks top to bottom at their measured heights.

        When they all fit, each takes its natural height. When they do not, each
        is guaranteed a couple of lines and the rest of the space is shared in
        proportion to how much each wanted. Whatever a block does not use passes
        to the next one, so there are no dead gaps and nothing overlaps.
        """
        prepared = []
        for block in blocks:
            text = self._clean(block.get('text')) if block.get('clean', True) \
                else (block.get('text') or '').strip()
            if text:
                prepared.append(dict(block, text=text))
        if not prepared:
            return top
        labels = sum(self.LABEL_H for block in prepared if block.get('label'))
        avail = int(bottom - top - labels - gap * (len(prepared) - 1))
        natural = [typeset.measure(b['text'], int(width), b.get('max_pt', 10.0),
                                   bold=b.get('bold', False))
                   for b in prepared]
        if sum(natural) <= avail:
            alloc = natural
        else:
            floors = [min(n, int(typeset.line_pitch(b.get('min_pt', 8.5), 1.2)
                                 * b.get('floor_lines', 2)))
                      for n, b in zip(natural, prepared)]
            spare = max(0, avail - sum(floors))
            extra = [n - f for n, f in zip(natural, floors)]
            share = float(sum(extra) or 1)
            alloc = [f + int(spare * e / share) for f, e in zip(floors, extra)]

        y, carry = top, 0
        for block, budget in zip(prepared, alloc):
            if block.get('label'):
                self._panel_label(slide, left, y, width, block['label'],
                                  color=block.get('label_color', GRAY_3), size=Pt(6.5))
                y += self.LABEL_H
            room = budget + carry
            used = self._prose(slide, left, y, width, room, block['text'],
                               max_pt=block.get('max_pt', 10.0),
                               min_pt=block.get('min_pt', 8.5),
                               color=block.get('color', BLACK),
                               bold=block.get('bold', False),
                               font=block.get('font'),
                               italic=block.get('italic', False),
                               label=block.get('note', block.get('label', '').title()),
                               clean=False)
            carry = room - used
            y += used + gap
        return y

    def _cites(self, slide, left, top, width, height, proof, *, size=7.5,
               color=IMPACT_BLUE, stacked=False):
        """Short, linked source labels for a proof slot.

        "AssortSmart Eng, pp. 1 to 2" and "globenewswire.com" rather than the
        raw path or a 180 character URL. The full string goes to the notes. A
        narrow column takes one source a line, since a run of labels wrapped
        mid name reads as one garbled citation.
        """
        entries = typeset.cites(proof)
        if not entries:
            return 0
        self._sources.append(proof)
        gap = int(Pt(3)) if stacked else 0

        def need(labels):
            if stacked:
                return sum(typeset.measure(label, int(width), size, 1.15)
                           for label in labels) + gap * (len(labels) - 1)
            return typeset.measure('  ·  '.join(labels), int(width), size, 1.15)

        shown = []
        for entry in entries:
            if need([label for label, _ in shown + [entry]]) > height and shown:
                break
            shown.append(entry)
        box = add_textbox(slide, left, top, width, height)
        tf = box.text_frame
        p = tf.paragraphs[0]
        p.line_spacing = 1.15
        for index, (label, url) in enumerate(shown):
            if index and stacked:
                p = tf.add_paragraph()
                p.line_spacing = 1.15
                p.space_before = Pt(3)
            elif index:
                sep = p.add_run()
                sep.text = '  ·  '
                set_run_font(sep, Pt(size), False, GRAY_3, self.theme.body_font)
            run = p.add_run()
            run.text = label
            set_run_font(run, Pt(size), False, color, self.theme.body_font)
            if url:
                run.hyperlink.address = url
        return min(int(height), need([label for label, _ in shown]))

    def _link(self, slide, left, top, width, label, url):
        box = add_textbox(slide, left, top, width, Inches(0.24))
        p = box.text_frame.paragraphs[0]
        p.line_spacing = 1.0
        run = p.add_run()
        run.text = label
        set_run_font(run, Pt(8.5), False, IMPACT_BLUE, self.theme.body_font)
        if url.lower().startswith('http'):
            run.hyperlink.address = url
        else:
            run.text = url[:90]
        return box

    def _table(self, slide, left, top, width, headers, rows, col_ratios,
               row_heights, header_height=Inches(0.3), font_pt=7.5):
        """A table with explicit fills, borders and fonts, and measured rows.

        Every row height is measured beforehand, so the table ends where the
        layout expects it to and nothing is drawn over its bottom rows.
        """
        total = len(rows) + 1
        frame = slide.shapes.add_table(total, len(headers), int(left), int(top),
                                       int(width), int(header_height + sum(row_heights)))
        table = frame.table
        tblPr = table._tbl.find(qn('a:tblPr'))
        if tblPr is not None:
            for node in tblPr.findall(qn('a:tableStyleId')):
                tblPr.remove(node)
            tblPr.set('firstRow', '0')
            tblPr.set('bandRow', '0')

        ratio_total = float(sum(col_ratios))
        for index, ratio in enumerate(col_ratios):
            table.columns[index].width = Emu(int(width * ratio / ratio_total))
        table.rows[0].height = int(header_height)
        for index, height in enumerate(row_heights, start=1):
            table.rows[index].height = int(height)

        for col, header in enumerate(headers):
            self._cell(table.cell(0, col), header, size=Pt(8.5), bold=True,
                       color=WHITE, fill=IMPACT_BLUE,
                       align=PP_ALIGN.LEFT if col in (0, len(headers) - 1) else PP_ALIGN.CENTER)
        for r, row in enumerate(rows, start=1):
            band = WHITE if r % 2 else OFF_WHITE
            for c, value in enumerate(row):
                text, color, bold, align = self._unpack_cell(value, c)
                self._cell(table.cell(r, c), text, size=Pt(font_pt), bold=bold,
                           color=color, fill=band, align=align)
        return table

    @staticmethod
    def _unpack_cell(value, column_index):
        if isinstance(value, dict):
            return (value.get('text', ''), value.get('color', BLACK),
                    value.get('bold', False),
                    value.get('align', PP_ALIGN.LEFT if column_index == 0 else PP_ALIGN.CENTER))
        return (str(value), BLACK, False,
                PP_ALIGN.LEFT if column_index == 0 else PP_ALIGN.CENTER)

    CELL_PAD_X = Inches(0.08)
    CELL_PAD_Y = Inches(0.05)

    def _cell(self, cell, text, size, bold, color, fill, align):
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
        cell.margin_left = self.CELL_PAD_X
        cell.margin_right = self.CELL_PAD_X
        cell.margin_top = self.CELL_PAD_Y
        cell.margin_bottom = self.CELL_PAD_Y
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = align
        p.line_spacing = 1.1
        run = p.add_run()
        run.text = text
        set_run_font(run, size, bold, color, self.theme.body_font)
        self._cell_borders(cell, GRAY_1)

    @staticmethod
    def _cell_borders(cell, color, width=Pt(0.75)):
        tcPr = cell._tc.get_or_add_tcPr()
        order = ['a:lnL', 'a:lnR', 'a:lnT', 'a:lnB']
        for tag in reversed(order):
            for node in tcPr.findall(qn(tag)):
                tcPr.remove(node)
            line = tcPr.makeelement(qn(tag), {'w': str(int(width)), 'cap': 'flat',
                                              'cmpd': 'sng', 'algn': 'ctr'})
            solid = line.makeelement(qn('a:solidFill'), {})
            srgb = line.makeelement(qn('a:srgbClr'), {'val': str(color)})
            solid.append(srgb)
            line.append(solid)
            tcPr.insert(0, line)

    # ── sections ───────────────────────────────────────────────────────────────
    # Every title is a (lead, emphasis) pair. The house template splits titles
    # into a Black phrase and an Impact Blue phrase, so the emphasis carries the
    # point of the slide. A section that runs to several slides says "2 of 4" in
    # the kicker rather than in the title, and numbering runs on across pages.

    def slide_cover(self):
        slide = self._slide(dark=True, patterned=True)
        self._held, self._sources = [], []
        self._logo(slide, dark=True, height=Inches(0.3))
        soft = mix(WHITE, IMPACT_BLUE, 0.4)

        kicker = 'Competitive battlecard  ·  %s' % SOLUTION_LABELS.get(self.solution, '')
        box = add_textbox(slide, MARGIN, Inches(1.22), CONTENT_W, Inches(0.22))
        write_paragraph(box.text_frame, kicker.upper(), Pt(8), bold=True, color=WHITE,
                        font=self.theme.body_font, space_after=0, line_spacing=1.0,
                        first=True)

        title = self.meta['competitor']
        title_size = fit_size(title, int(CONTENT_W), int(Inches(0.9)), 40, 22)
        title_box = add_textbox(slide, MARGIN, Inches(1.5), CONTENT_W, Inches(0.9))
        write_paragraph(title_box.text_frame, title, title_size, bold=True, color=WHITE,
                        font=self.theme.heading_font, space_after=0, line_spacing=1.0,
                        first=True)

        headline = self.meta.get('headline') or 'Know the rival. Lead with the outcome.'
        self._prose(slide, MARGIN, Inches(2.5), Inches(6.2), Inches(0.9), headline,
                    max_pt=12, min_pt=10, color=mix(WHITE, IMPACT_BLUE, 0.12),
                    label='Headline')

        # Only the facts that exist. A cover showing "Add an owner" is a draft.
        facts = [(label, value) for label, value in (
            ('Impact Analytics product', self.meta.get('ia_product')),
            ('Their category', self.meta.get('competitor_category')),
            ('Prepared for', self.meta.get('audience')),
            ('Owner', self.meta.get('owner')),
            ('Updated', self.meta.get('date')),
        ) if value]
        widths = {'Their category': 2.2}
        units = [widths.get(label, 1.0) for label, _ in facts]
        gap = Inches(0.22)
        span = CONTENT_W - gap * max(0, len(facts) - 1)
        left = MARGIN
        top = Inches(3.66)
        for (label, value), unit in zip(facts, units):
            col_w = int(span * unit / sum(units))
            self._panel_label(slide, left, top, col_w, label, color=soft, size=Pt(6.5))
            self._prose(slide, left, top + self.LABEL_H, col_w, Inches(0.72), value,
                        max_pt=9.5, min_pt=8, color=WHITE, label=label)
            left += col_w + gap

        strip = add_textbox(slide, MARGIN, Inches(4.86), CONTENT_W, Inches(0.22))
        write_paragraph(strip.text_frame, self.meta['confidentiality'].upper(), Pt(7),
                        bold=True, color=soft, font=self.theme.body_font, space_after=0,
                        line_spacing=1.0, first=True)
        self.page += 1
        self._notes(slide, 'Battlecard for %s. Owner: %s. Confirm every competitor claim '
                           'against a dated source before you use it in a deal.'
                    % (self.meta['competitor'], self.meta.get('owner') or 'unassigned'))

    def slide_how_to_use(self):
        items = self.card.get('how_to_use') or []
        if not items:
            return
        slide = self._page(('How to use this ', 'battlecard'))
        left_w = Inches(5.75)
        self._panel(slide, MARGIN, BODY_TOP, left_w, BODY_H)
        self._panel_label(slide, MARGIN + PAD, BODY_TOP + Inches(0.2), left_w - 2 * PAD,
                          'Working rules')
        rest = self._bullets(slide, MARGIN + PAD, BODY_TOP + Inches(0.48), left_w - 2 * PAD,
                             BODY_H - Inches(0.66), items, max_pt=11, min_pt=9,
                             bullet_color=IMPACT_BLUE, label='Working rule')
        for entry in rest:
            self._hold('Working rule', entry['full'] or entry['text'])

        right_left = MARGIN + left_w + GUTTER
        right_w = CONTENT_W - left_w - GUTTER
        self._panel(slide, right_left, BODY_TOP, right_w, BODY_H, fill=IMPACT_BLUE)
        self._panel_label(slide, right_left + PAD, BODY_TOP + Inches(0.2), right_w - 2 * PAD,
                          'Win theme', color=mix(WHITE, IMPACT_BLUE, 0.4))
        self._prose(slide, right_left + PAD, BODY_TOP + Inches(0.5), right_w - 2 * PAD,
                    BODY_H - Inches(0.7),
                    self.meta.get('win_theme') or 'Name the one reason this buyer switches.',
                    max_pt=13, min_pt=10, color=WHITE, label='Win theme')
        self._notes(slide, 'Read this slide before the call, not during it.')

    def slide_snapshot(self):
        """Company facts and recent moves, on one slide when they fit.

        A researched snapshot runs to fifteen hundred characters of facts with
        their caveats, which needs twice the height a half width panel has. Rather
        than trim "Employees" to "Trackers disagree.", the facts take the full
        width and the recent moves get a slide of their own.
        """
        snapshot = self.card.get('snapshot', {})
        fields = [
            ('Headquarters', snapshot.get('headquarters')),
            ('Founded', snapshot.get('founded')),
            ('Employees', snapshot.get('employees')),
            ('Ownership', snapshot.get('ownership')),
            ('Funding', snapshot.get('funding')),
            ('Target segment', snapshot.get('target_segment')),
            ('Go to market', snapshot.get('go_to_market')),
            ('Deployment', snapshot.get('deployment')),
        ]
        facts = []
        for label, value in fields:
            clean, found = typeset.split_sources(value or '')
            if clean:
                facts.append((label, clean, found))
        moves = snapshot.get('recent_moves') or []
        customers, customer_sources = typeset.split_sources(
            snapshot.get('notable_customers') or '')
        if not facts and not moves and not customers:
            return

        narrow_w = Inches(5.95)
        if self._facts_fit(facts, narrow_w - 2 * PAD, customers):
            slide = self._page(('Competitor ', 'snapshot'))
            self._facts_card(slide, MARGIN, narrow_w, facts, customers, customer_sources)
            right_left = MARGIN + narrow_w + GUTTER
            self._moves_card(slide, right_left, CONTENT_W - narrow_w - GUTTER, moves)
            self._notes(slide, 'Every fact on this slide needs a dated source. '
                               'Refresh it each quarter.')
            return

        slide = self._page(('Competitor ', 'snapshot'))
        self._facts_card(slide, MARGIN, CONTENT_W, facts, customers, customer_sources)
        self._notes(slide, 'Every fact on this slide needs a dated source. Refresh it each quarter.')
        if moves:
            slide = self._page(('Recent ', 'moves'))
            self._moves_card(slide, MARGIN, CONTENT_W, moves)
            self._notes(slide, 'Check their newsroom and LinkedIn before every call. A move '
                               'older than a quarter is background, not news.')

    SNAPSHOT_ROW_GAP = Inches(0.1)

    def _facts_fit(self, facts, inner_w, customers):
        """True when every fact fits in full at a legible size in this width."""
        cell_w = (inner_w - Inches(0.24)) / 2
        rows = [facts[i:i + 2] for i in range(0, len(facts), 2)]
        need = sum(self.LABEL_H + self.SNAPSHOT_ROW_GAP +
                   max(typeset.measure(text, int(cell_w), 8.5) for _, text, _ in row)
                   for row in rows)
        if customers:
            need += self.LABEL_H + typeset.measure(customers, int(inner_w), 8.5)
        return need <= BODY_H - Inches(0.6)

    def _facts_card(self, slide, left, width, facts, customers, customer_sources):
        self._panel(slide, left, BODY_TOP, width, BODY_H)
        inner_left = left + PAD
        inner_w = width - 2 * PAD
        self._panel_label(slide, inner_left, BODY_TOP + Inches(0.18), inner_w, 'Company facts')
        col_gap = Inches(0.24)
        cell_w = (inner_w - col_gap) / 2
        bottom = BODY_TOP + BODY_H - Inches(0.14)
        cust_h = 0
        if customers:
            self._sources.extend(customer_sources)
            cust_h = self.LABEL_H + min(typeset.measure(customers, int(inner_w), 9),
                                        int(Inches(0.5))) + Inches(0.08)

        rows = [facts[i:i + 2] for i in range(0, len(facts), 2)]
        y = BODY_TOP + Inches(0.46)
        row_gap = self.SNAPSHOT_ROW_GAP
        # Rows get the height they need, not an equal share: "Dallas, Texas." and
        # a funding history are not the same size.
        avail = int(bottom - cust_h - y - len(rows) * (self.LABEL_H + row_gap))
        # One size for the whole grid: the largest at which every fact fits.
        grid_pt = 8.5
        for pt in typeset._sizes(10, 8.5):
            if sum(max(typeset.measure(text, int(cell_w), pt) for _, text, _ in row)
                   for row in rows) <= avail:
                grid_pt = pt
                break
        natural = [max(typeset.measure(text, int(cell_w), grid_pt) for _, text, _ in row)
                   for row in rows]
        if sum(natural) <= avail:
            alloc = natural
        else:
            floors = [min(n, int(typeset.line_pitch(8.5, 1.2) * 3)) for n in natural]
            spare = max(0, avail - sum(floors))
            extra = [n - f for n, f in zip(natural, floors)]
            share = float(sum(extra) or 1)
            alloc = [f + int(spare * e / share) for f, e in zip(floors, extra)]
        carry = 0
        for row, budget in zip(rows, alloc):
            room = budget + carry
            used = []
            for col, (label, text, found) in enumerate(row):
                self._sources.extend(found)
                x = inner_left + col * (cell_w + col_gap)
                self._panel_label(slide, x, y, cell_w, label, color=GRAY_3, size=Pt(6.5))
                used.append(self._prose(slide, x, y + self.LABEL_H, cell_w, room, text,
                                        max_pt=grid_pt, min_pt=grid_pt, label=label,
                                        clean=False))
            carry = room - max(used)
            y += self.LABEL_H + max(used) + row_gap

        if customers:
            self._panel_label(slide, inner_left, y, inner_w, 'Named customers',
                              color=GRAY_3, size=Pt(6.5))
            self._prose(slide, inner_left, y + self.LABEL_H, inner_w,
                        bottom - y - self.LABEL_H, customers, max_pt=10, min_pt=8.5,
                        label='Named customers', clean=False)

    def _moves_card(self, slide, left, width, moves):
        inner = width - 2 * PAD
        self._panel(slide, left, BODY_TOP, width, BODY_H)
        self._panel_label(slide, left + PAD, BODY_TOP + Inches(0.18), inner, 'Recent moves')
        rest = self._bullets(slide, left + PAD, BODY_TOP + Inches(0.46), inner,
                             BODY_H - Inches(0.62),
                             moves or ['Add funding, product or leadership news, with a source link.'],
                             max_pt=11, min_pt=9, bullet_color=self.theme.accent,
                             label='Recent move')
        for entry in rest:
            self._register(entry)
            self._hold('Recent move', entry['full'] or entry['text'])

    def slide_positioning(self):
        positioning = self.card.get('positioning', {})
        if not any(positioning.values()):
            return
        slide = self._page(('Positioning ', 'face off'))
        col_w = (CONTENT_W - GUTTER) / 2
        panel_h = BODY_H - Inches(1.1)
        inner = col_w - 2 * PAD

        self._panel(slide, MARGIN, BODY_TOP, col_w, panel_h)
        self._panel_label(slide, MARGIN + PAD, BODY_TOP + Inches(0.2), inner, 'They say',
                          color=GRAY_3)
        self._prose(slide, MARGIN + PAD, BODY_TOP + Inches(0.48), inner,
                    panel_h - Inches(0.64),
                    positioning.get('their_claim') or 'Paste their positioning line.',
                    max_pt=12.5, min_pt=10, label='They say')

        right = MARGIN + col_w + GUTTER
        self._panel(slide, right, BODY_TOP, col_w, panel_h, fill=IMPACT_BLUE)
        self._panel_label(slide, right + PAD, BODY_TOP + Inches(0.2), inner, 'We say',
                          color=mix(WHITE, IMPACT_BLUE, 0.4))
        self._prose(slide, right + PAD, BODY_TOP + Inches(0.48), inner,
                    panel_h - Inches(0.64),
                    positioning.get('our_claim') or 'Write the Impact Analytics line.',
                    max_pt=12.5, min_pt=10, color=WHITE, label='We say')

        wedge_top = BODY_TOP + panel_h + Inches(0.14)
        wedge_h = BODY_H - panel_h - Inches(0.14)
        self._panel(slide, MARGIN, wedge_top, CONTENT_W, wedge_h)
        self._panel_label(slide, MARGIN + PAD, wedge_top + Inches(0.14), CONTENT_W - 2 * PAD,
                          'The wedge')
        self._prose(slide, MARGIN + PAD, wedge_top + Inches(0.38), CONTENT_W - 2 * PAD,
                    wedge_h - Inches(0.5),
                    positioning.get('wedge') or 'Name the gap this buyer feels weekly.',
                    max_pt=11, min_pt=9, label='The wedge')
        self._notes(slide, 'Say the wedge in the buyer own words. Quote them back.')

    def _two_lists(self, title, left_spec, right_spec, note):
        """Two bulleted cards side by side, paginated so every item is shown.

        Each spec is (label, items, label colour, bullet colour).
        """
        col_w = (CONTENT_W - GUTTER) / 2
        inner = col_w - 2 * PAD
        list_h = BODY_H - Inches(0.66)
        prepared = [self._prep(items, inner, 9, max_lines=4, label=label)
                    for label, items, _, _ in (left_spec, right_spec)]
        split = [self._split(entries, inner, list_h, 11, 9) for entries in prepared]
        total = max(len(split[0]), len(split[1]))
        # Both columns share the page count, so each spreads across all of them.
        split = [self._split(entries, inner, list_h, 11, 9, pages=total)
                 for entries in prepared]
        total = max(len(split[0]), len(split[1]))
        for page in range(total):
            slide = self._page(title, counter=(page + 1, total))
            for index, (label, items, label_color, bullet_color) in enumerate((left_spec, right_spec)):
                left = MARGIN + index * (col_w + GUTTER)
                self._panel(slide, left, BODY_TOP, col_w, BODY_H)
                self._panel_label(slide, left + PAD, BODY_TOP + Inches(0.2), inner,
                                  label, color=label_color)
                group = split[index][page] if page < len(split[index]) else []
                if group:
                    self._bullets(slide, left + PAD, BODY_TOP + Inches(0.5), inner,
                                  list_h, group, max_pt=11, min_pt=9,
                                  bullet_color=bullet_color)
                elif page == 0:
                    self._prose(slide, left + PAD, BODY_TOP + Inches(0.5), inner,
                                Inches(0.4), 'Nothing recorded yet.', max_pt=9.5,
                                min_pt=9, color=GRAY_3)
            self._notes(slide, note)

    def slide_strengths_weaknesses(self):
        strengths = self.card.get('their_strengths') or []
        weaknesses = self.card.get('their_weaknesses') or []
        if not strengths and not weaknesses:
            return
        name = self.meta['competitor']
        self._two_lists(('Where they win, ', 'where they fall short'),
                        ('Where %s wins' % name, strengths, GRAY_3, GRAY_3),
                        ('Where %s falls short' % name, weaknesses, IMPACT_BLUE, IMPACT_BLUE),
                        'An honest read of their strengths buys credibility for the rest.')

    def slide_why_we_win(self):
        advantages = [row for row in (self.card.get('our_advantages') or [])
                      if row.get('title') or row.get('detail')]
        if not advantages:
            return
        sizes = typeset.balance(len(advantages), 3)
        number, start = 0, 0
        for page, size in enumerate(sizes, 1):
            group = advantages[start:start + size]
            start += size
            slide = self._page(('Why Impact Analytics ', 'wins'), counter=(page, len(sizes)))
            col_w = (CONTENT_W - GUTTER * (size - 1)) / size
            inner = col_w - 2 * PAD
            # Titles are fitted as a set, at one size, and every detail starts at
            # the same height. Cards whose text begins at different depths read
            # as a draft even when nothing overflows.
            title_top = BODY_TOP + Inches(0.32)
            title_room = int(Inches(0.72))
            title_pt = 13.0
            while title_pt > 10.5 and any(
                    typeset.measure(self._clean(row.get('title')), int(inner), title_pt,
                                    bold=True) > title_room for row in group):
                title_pt -= 0.5
            title_h = max(typeset.measure(self._clean(row.get('title')), int(inner),
                                          title_pt, bold=True) for row in group)
            detail_top = title_top + min(title_h, title_room) + Inches(0.14)
            proof_room = lambda row: Inches(0.56) if (row.get('proof') or '').strip() else 0
            detail_pt = self._group_pt(
                [(row.get('detail'), inner,
                  BODY_TOP + BODY_H - Inches(0.14) - proof_room(row) - detail_top)
                 for row in group], 10, 8.5)
            for index, row in enumerate(group):
                number += 1
                left = MARGIN + index * (col_w + GUTTER)
                self._panel(slide, left, BODY_TOP, col_w, BODY_H)
                self._pill(slide, left + PAD, BODY_TOP - Inches(0.1), inner,
                           '%02d' % number, width=Inches(0.52))
                self._prose(slide, left + PAD, title_top, inner, title_room,
                            row.get('title'), max_pt=title_pt, min_pt=min(title_pt, 10.5),
                            bold=True, font=self.theme.heading_font,
                            label='Advantage %02d' % number)
                proof = (row.get('proof') or '').strip()
                proof_h = Inches(0.56) if proof else 0
                bottom = BODY_TOP + BODY_H - Inches(0.14) - proof_h
                self._prose(slide, left + PAD, detail_top, inner, bottom - detail_top,
                            row.get('detail'), max_pt=detail_pt, min_pt=detail_pt,
                            label='Advantage %02d, detail' % number)
                if proof:
                    proof_top = BODY_TOP + BODY_H - Inches(0.14) - proof_h
                    self._panel_label(slide, left + PAD, proof_top, inner, 'Proof',
                                      color=GRAY_3, size=Pt(6.5))
                    self._cites(slide, left + PAD, proof_top + self.LABEL_H, inner,
                                proof_h - self.LABEL_H, proof)
            self._notes(slide, 'Lead with the outcome. Name the product second.')

    # The comparison matrix has its own pagination, by measured row height.
    MATRIX_COLS = (0.25, 0.115, 0.115, 0.52)
    MATRIX_PT = 7.5
    MATRIX_NOTE_LINES = 6

    def slide_comparison(self):
        rows = self.card.get('comparison') or []
        if not rows:
            return
        widths = [int(CONTENT_W * r / sum(self.MATRIX_COLS)) - 2 * self.CELL_PAD_X
                  for r in self.MATRIX_COLS]
        cap = int(typeset.line_pitch(self.MATRIX_PT, 1.1) * self.MATRIX_NOTE_LINES)
        entries = []
        for row in rows:
            note, found = typeset.split_sources(row.get('note', ''))
            full = ''
            if typeset.measure(note, widths[3], self.MATRIX_PT, 1.1) > cap:
                full = note
                note = typeset.trim_to(note, widths[3], cap, self.MATRIX_PT, 1.1)
            capability = (row.get('capability') or '').strip()
            height = max(typeset.measure(capability, widths[0], 8, 1.1),
                         typeset.measure(note, widths[3], self.MATRIX_PT, 1.1),
                         int(typeset.line_pitch(8, 1.1)))
            height = max(int(Inches(0.3)), height + 2 * self.CELL_PAD_Y + int(Inches(0.04)))
            entries.append({'row': row, 'capability': capability, 'note': note,
                            'full': full, 'sources': found, 'height': height})

        header_h = Inches(0.3)
        legend_h = Inches(0.24)
        room = int(BODY_H - header_h - legend_h)
        pages = self._matrix_pages(entries, room)
        name = self.meta['competitor']
        for index, group in enumerate(pages, 1):
            slide = self._page(('Head to head: ', 'AssortSmart vs %s' % name
                                if self.meta.get('ia_product') == 'AssortSmart' else name),
                               counter=(index, len(pages)))
            table_rows = []
            for entry in group:
                self._sources.extend(entry['sources'])
                if entry['full']:
                    self._hold(entry['capability'], entry['full'])
                row = entry['row']
                table_rows.append([
                    {'text': entry['capability'], 'bold': True, 'align': PP_ALIGN.LEFT},
                    self._rating_cell(row.get('ia')),
                    self._rating_cell(row.get('competitor')),
                    {'text': entry['note'], 'align': PP_ALIGN.LEFT, 'color': BLACK},
                ])
            product = self.meta.get('ia_product') or 'Impact Analytics'
            self._table(slide, MARGIN, BODY_TOP, CONTENT_W,
                        ['Capability', product, name, 'What to say'],
                        table_rows, col_ratios=list(self.MATRIX_COLS),
                        row_heights=[e['height'] for e in group],
                        header_height=header_h, font_pt=self.MATRIX_PT)
            # A fixed band under the body, never after the table, so the legend
            # cannot land on a row however tall the rows run.
            self._legend(slide, MARGIN, BODY_TOP + BODY_H - Inches(0.2))
            self._notes(slide, 'Show this only when the buyer asks for a direct comparison. '
                               'Defend every row with evidence.')

    @staticmethod
    def _matrix_pages(entries, room):
        """Pages of rows by height, balanced so no page is left with a stub.

        Greedy filling decides how many pages are needed; then each page aims for
        an even share of the total height, which is how 22 rows became 4 pages of
        5 or 6 instead of 7, 7, 7 and a lone row.
        """
        greedy, used = 1, 0
        for entry in entries:
            if used + entry['height'] > room and used:
                greedy += 1
                used = 0
            used += entry['height']
        total = sum(e['height'] for e in entries)
        target = total / float(greedy)
        pages, current, used = [], [], 0
        for index, entry in enumerate(entries):
            left_pages = greedy - len(pages)
            if current and (used + entry['height'] > room or
                            (used + entry['height'] / 2.0 > target and left_pages > 1)):
                pages.append(current)
                current, used = [], 0
            current.append(entry)
            used += entry['height']
        if current:
            pages.append(current)
        return pages

    def _rating_cell(self, rating):
        key = rating if rating in RATING_LABELS else 'unknown'
        return {'text': RATING_LABELS[key], 'color': RATING_COLORS[key],
                'bold': key == 'strong', 'align': PP_ALIGN.CENTER}

    def _legend(self, slide, left, top):
        box = add_textbox(slide, left, top, CONTENT_W, Inches(0.16))
        p = box.text_frame.paragraphs[0]
        p.line_spacing = 1.0
        for index, key in enumerate(('strong', 'partial', 'none', 'unknown')):
            run = p.add_run()
            run.text = ('      ' if index else '') + RATING_LABELS[key]
            set_run_font(run, Pt(7), True, RATING_COLORS[key], self.theme.body_font)
            gloss = p.add_run()
            gloss.text = {'strong': ' ships today', 'partial': ' partial coverage',
                          'none': ' not available', 'unknown': ' needs research'}[key]
            set_run_font(gloss, Pt(7), False, GRAY_3, self.theme.body_font)

    def slide_objections(self):
        rows = [row for row in (self.card.get('objections') or []) if row.get('objection')]
        if not rows:
            return
        sizes = typeset.balance(len(rows), 2)
        start = 0
        for page, size in enumerate(sizes, 1):
            group = rows[start:start + size]
            start += size
            slide = self._page(('Objection ', 'handling'), counter=(page, len(sizes)))
            row_h = (BODY_H - GUTTER * (size - 1)) / size
            inner = CONTENT_W - 2 * PAD
            col_gap = Inches(0.22)
            ratios = (0.27, 0.51, 0.22)
            widths = [int((inner - 2 * col_gap) * r) for r in ratios]
            text_h = row_h - Inches(0.28) - self.LABEL_H
            they_pt = self._group_pt([(r.get('objection'), widths[0], text_h) for r in group],
                                     11, 9.5, bold=True)
            we_pt = self._group_pt([(r.get('response'), widths[1], text_h) for r in group],
                                   10, 8.5)
            for index, row in enumerate(group):
                top = BODY_TOP + index * (row_h + GUTTER)
                self._panel(slide, MARGIN, top, CONTENT_W, row_h)
                bottom = top + row_h - Inches(0.14)
                x = MARGIN + PAD
                self._stack(slide, x, top + Inches(0.14), widths[0], bottom, [
                    dict(label='They say', text=row.get('objection'), max_pt=they_pt,
                         min_pt=they_pt, bold=True, font=self.theme.heading_font,
                         label_color=GRAY_3, note='They say')])
                x += widths[0] + col_gap
                self._stack(slide, x, top + Inches(0.14), widths[1], bottom, [
                    dict(label='We say', text=row.get('response'), max_pt=we_pt,
                         min_pt=we_pt, label_color=IMPACT_BLUE,
                         note='We say, to "%s"' % (row.get('objection') or '')[:60])])
                x += widths[1] + col_gap
                if row.get('proof'):
                    self._panel_label(slide, x, top + Inches(0.14), widths[2], 'Proof',
                                      color=GRAY_3, size=Pt(6.5))
                    self._cites(slide, x, top + Inches(0.14) + self.LABEL_H, widths[2],
                                bottom - top - Inches(0.14) - self.LABEL_H, row['proof'],
                                size=8, stacked=True)
            self._notes(slide, 'Answer the objection once, then return to the outcome.')

    def slide_landmines(self):
        rows = [row for row in (self.card.get('landmines') or []) if row.get('question')]
        if not rows:
            return
        sizes = typeset.balance(len(rows), 3)
        start = 0
        for page, size in enumerate(sizes, 1):
            group = rows[start:start + size]
            start += size
            slide = self._page(('Landmines ', 'to set'), counter=(page, len(sizes)))
            col_w = (CONTENT_W - GUTTER * (size - 1)) / size
            inner = col_w - 2 * PAD
            gap = Inches(0.14)
            room = BODY_H - Inches(0.3) - 3 * self.LABEL_H - 2 * gap
            ask_pt = self._group_pt([(r.get('question'), inner,
                                      typeset.line_pitch(12, 1.2) * 4) for r in group],
                                    12, 10, bold=True)
            body_pt = self._group_body_pt(group, inner, room, ask_pt)
            for index, row in enumerate(group):
                left = MARGIN + index * (col_w + GUTTER)
                self._panel(slide, left, BODY_TOP, col_w, BODY_H)
                self._stack(slide, left + PAD, BODY_TOP + Inches(0.16), inner,
                            BODY_TOP + BODY_H - Inches(0.14), [
                                dict(label='Ask this', label_color=IMPACT_BLUE,
                                     text=row.get('question'), max_pt=ask_pt,
                                     min_pt=ask_pt, bold=True,
                                     font=self.theme.heading_font,
                                     floor_lines=4, note='Question'),
                                dict(label='Why it lands', text=row.get('why'),
                                     max_pt=body_pt, min_pt=body_pt,
                                     note='Why it lands, "%s"' % row['question'][:50]),
                                dict(label='Listen for', text=row.get('listen_for'),
                                     max_pt=body_pt, min_pt=body_pt, color=IMPACT_BLUE,
                                     note='Listen for, "%s"' % row['question'][:50]),
                            ], gap=gap)
            self._notes(slide, 'Set one landmine per call. More than one sounds rehearsed.')

    def _group_body_pt(self, group, width, room, ask_pt, max_pt=9.5, min_pt=8.5):
        """The largest size at which every landmine's two body blocks fit
        beneath its question, so the cards on a page share one size."""
        for pt in typeset._sizes(max_pt, min_pt):
            if all(typeset.measure(self._peek(r.get('question')), int(width), ask_pt,
                                   bold=True)
                   + typeset.measure(self._peek(r.get('why')), int(width), pt)
                   + typeset.measure(self._peek(r.get('listen_for')), int(width), pt)
                   <= room for r in group):
                return pt
        return min_pt

    @staticmethod
    def _peek(text):
        """Body text as it will be drawn, without collecting its sources."""
        return typeset.split_sources(text or '')[0]

    def slide_discovery(self):
        rows = [row for row in (self.card.get('discovery') or []) if row.get('questions')]
        if not rows:
            return
        sizes = typeset.balance(len(rows), 3)
        start = 0
        for page, size in enumerate(sizes, 1):
            group = rows[start:start + size]
            start += size
            slide = self._page(('Discovery ', 'questions'), counter=(page, len(sizes)))
            col_w = (CONTENT_W - GUTTER * (size - 1)) / size
            inner = col_w - 2 * PAD
            for index, row in enumerate(group):
                left = MARGIN + index * (col_w + GUTTER)
                self._panel(slide, left, BODY_TOP, col_w, BODY_H)
                used = self._prose(slide, left + PAD, BODY_TOP + Inches(0.18), inner,
                                   Inches(0.5), row.get('theme', ''), max_pt=12.5,
                                   min_pt=10.5, bold=True, font=self.theme.heading_font,
                                   label='Discovery theme')
                top = BODY_TOP + Inches(0.18) + used + Inches(0.14)
                rest = self._bullets(slide, left + PAD, top, inner,
                                     BODY_TOP + BODY_H - Inches(0.14) - top,
                                     row.get('questions') or [], max_pt=10.5, min_pt=9,
                                     bullet_color=IMPACT_BLUE, label=row.get('theme', ''))
                for entry in rest:
                    self._register(entry)
                    self._hold(row.get('theme', 'Question'), entry['full'] or entry['text'])
            self._notes(slide, 'Run discovery before any slide goes on the screen.')

    @staticmethod
    def _stat_pt(value, inner_w):
        # A stat is short, bold display type, mostly digits and capitals, which
        # run near 0.66 em a character, well past the prose average the general
        # measure uses. Sized directly so "11 March 2026" stays on one line.
        room_pt = (inner_w - Inches(0.14)) / 12700.0
        return max(14.0, min(30.0, room_pt / (max(len(value), 1) * 0.66)))

    def _stat(self, slide, left, top, width, height, row, value_pt=None):
        """The house stat card: a tinted number panel, then the label and detail.

        The number is fitted to a single line, so "11 March 2026" sits as
        comfortably as "35%", and everything below it flows to the card's foot.
        """
        self._panel(slide, left, top, width, height)
        inner_w = width - 2 * PAD
        panel_h = Inches(0.66)
        tint = self._panel(slide, left + PAD, top + PAD, inner_w, panel_h,
                           fill=self.stat_tint, shadow=False)
        value = self._clean(row.get('stat', '')) or 'Add stat'
        pt = value_pt or self._stat_pt(value, inner_w)
        tf = prepare_text_frame(tint, margin=Inches(0.07), anchor=MSO_ANCHOR.MIDDLE)
        write_paragraph(tf, value, Pt(pt), bold=True, color=IMPACT_BLUE,
                        font=self.theme.heading_font, align=PP_ALIGN.CENTER,
                        space_after=0, line_spacing=1.0, first=True)

        source = (row.get('source') or '').strip()
        source_h = Inches(0.42) if source else 0
        bottom = top + height - PAD - source_h
        self._stack(slide, left + PAD, top + PAD + panel_h + Inches(0.14), inner_w, bottom, [
            dict(text=row.get('label'), max_pt=11.5, min_pt=10, italic=True,
                 floor_lines=2, note='Proof point'),
            dict(text=row.get('detail'), max_pt=9, min_pt=8.5, color=BLACK,
                 note='Proof point, "%s"' % (row.get('label') or '')[:50]),
        ], gap=Inches(0.1))
        if source:
            self._panel_label(slide, left + PAD, bottom, inner_w, 'Source',
                              color=GRAY_3, size=Pt(6.5))
            self._cites(slide, left + PAD, bottom + self.LABEL_H, inner_w,
                        source_h - self.LABEL_H, source)

    def slide_proof_points(self):
        rows = [row for row in (self.card.get('proof_points') or [])
                if row.get('stat') or row.get('label')]
        if not rows:
            return
        sizes = typeset.balance(len(rows), 4)
        start = 0
        for page, size in enumerate(sizes, 1):
            group = rows[start:start + size]
            start += size
            slide = self._page(('Proof ', 'points'), counter=(page, len(sizes)))
            col_w = (CONTENT_W - GUTTER * (size - 1)) / size
            # One number size across the row, set by the longest value, so a
            # date beside a percentage does not read as a different kind of fact.
            value_pt = min(self._stat_pt(self._peek(row.get('stat')) or 'Add stat',
                                         col_w - 2 * PAD) for row in group)
            for index, row in enumerate(group):
                left = MARGIN + index * (col_w + GUTTER)
                self._stat(slide, left, BODY_TOP, col_w, BODY_H, row, value_pt)
            self._notes(slide, 'Quote the number, then name the customer situation behind '
                               'it. Carry the source: a stat you cannot attribute loses the '
                               'room. Use results from 2025 or later and retire anything older.')

    def slide_talk_track(self):
        track = self.card.get('talk_track', {})
        blocks = [
            ('Positioning statement', track.get('positioning', '')),
            ('Thirty second pitch', track.get('elevator', '')),
            ('Discovery opener', track.get('discovery_open', '')),
            ('The trap question', track.get('trap', '')),
        ]
        blocks = [(label, text) for label, text in blocks if text]
        if not blocks:
            return
        slide = self._page(('Talk ', 'track'))
        cols = 2 if len(blocks) > 1 else 1
        rows = math.ceil(len(blocks) / cols)
        col_w = (CONTENT_W - GUTTER * (cols - 1)) / cols
        row_h = (BODY_H - GUTTER * (rows - 1)) / rows
        track_pt = self._group_pt([(text, col_w - 2 * PAD, row_h - Inches(0.52))
                                   for _, text in blocks], 11, 9)
        for index, (label, text) in enumerate(blocks):
            col, row = index % cols, index // cols
            left = MARGIN + col * (col_w + GUTTER)
            top = BODY_TOP + row * (row_h + GUTTER)
            highlight = index == 0
            self._panel(slide, left, top, col_w, row_h,
                        fill=IMPACT_BLUE if highlight else WHITE)
            self._panel_label(slide, left + PAD, top + Inches(0.14), col_w - 2 * PAD, label,
                              color=mix(WHITE, IMPACT_BLUE, 0.4) if highlight else IMPACT_BLUE,
                              size=Pt(7))
            self._prose(slide, left + PAD, top + Inches(0.38), col_w - 2 * PAD,
                        row_h - Inches(0.52), text, max_pt=track_pt, min_pt=track_pt,
                        color=WHITE if highlight else BLACK, label=label)
        self._notes(slide, 'Say it out loud twice before the call. Cut any sentence that '
                           'does not land.')

    def slide_dos_donts(self):
        dos = self.card.get('dos') or []
        donts = self.card.get('donts') or []
        if not dos and not donts:
            return
        self._two_lists(('Do ', 'and do not'),
                        ('Do', dos, IMPACT_BLUE, IMPACT_BLUE),
                        ('Do not', donts, GRAY_3, GRAY_3),
                        'These rules keep the conversation about value, not about the rival.')

    def slide_pricing(self):
        pricing = self.card.get('pricing', {})
        notes = pricing.get('notes') or []
        if not any((pricing.get('ia_model'), pricing.get('competitor_model'), notes)):
            return
        slide = self._page(('Pricing and ', 'packaging'))
        col_w = (CONTENT_W - GUTTER) / 2
        rules = notes or ['Record only what the buyer states or the vendor publishes.']
        # The ground rules panel takes the height its rules need at full size,
        # within limits, and the two model panels take the rest.
        need = typeset.measure_list([self._peek(rule) for rule in rules],
                                    int(CONTENT_W - 2 * PAD), 9.5) + Inches(0.5)
        note_h = max(Inches(1.0), min(int(need), int(BODY_H * 0.55)))
        panel_h = BODY_H - note_h - Inches(0.14)
        pairs = (
            ('Impact Analytics', pricing.get('ia_model', ''), IMPACT_BLUE, WHITE),
            (self.meta['competitor'], pricing.get('competitor_model', ''), WHITE, BLACK),
        )
        for index, (label, text, fill, ink) in enumerate(pairs):
            left = MARGIN + index * (col_w + GUTTER)
            self._panel(slide, left, BODY_TOP, col_w, panel_h, fill=fill)
            self._panel_label(slide, left + PAD, BODY_TOP + Inches(0.16), col_w - 2 * PAD,
                              label,
                              color=mix(WHITE, IMPACT_BLUE, 0.4) if index == 0 else IMPACT_BLUE)
            self._prose(slide, left + PAD, BODY_TOP + Inches(0.42), col_w - 2 * PAD,
                        panel_h - Inches(0.56), text or 'Add detail.',
                        max_pt=11, min_pt=9, color=ink, label=label)
        note_top = BODY_TOP + panel_h + Inches(0.14)
        self._panel(slide, MARGIN, note_top, CONTENT_W, note_h)
        self._panel_label(slide, MARGIN + PAD, note_top + Inches(0.13), CONTENT_W - 2 * PAD,
                          'Ground rules', color=GRAY_3, size=Pt(7))
        rest = self._bullets(slide, MARGIN + PAD, note_top + Inches(0.36), CONTENT_W - 2 * PAD,
                             note_h - Inches(0.46), rules,
                             max_pt=9.5, min_pt=8.5, bullet_color=GRAY_3, label='Ground rule')
        for entry in rest:
            self._register(entry)
            self._hold('Ground rule', entry['full'] or entry['text'])
        self._notes(slide, 'Never quote a rival price you cannot source.')

    def slide_next_steps(self):
        steps = [step for step in (self.card.get('next_steps') or []) if step]
        resources = self.card.get('resources') or []
        if not steps and not resources:
            return
        slide = self._page(('Next steps ', 'and resources'))
        left_w = Inches(5.95)
        self._panel(slide, MARGIN, BODY_TOP, left_w, BODY_H)
        self._panel_label(slide, MARGIN + PAD, BODY_TOP + Inches(0.2), left_w - 2 * PAD,
                          'Move the deal forward')
        text_left = MARGIN + PAD + Inches(0.34)
        text_w = left_w - 2 * PAD - Inches(0.34)
        bottom = BODY_TOP + BODY_H - Inches(0.14)
        y = BODY_TOP + Inches(0.52)
        for index, step in enumerate(steps):
            remaining = len(steps) - index
            budget = (bottom - y) / remaining - Inches(0.1)
            if budget < typeset.line_pitch(9, 1.2):
                self._hold('Next step %d' % (index + 1), step)
                continue
            marker = add_textbox(slide, MARGIN + PAD, y - Inches(0.02), Inches(0.3), Inches(0.28))
            write_paragraph(marker.text_frame, str(index + 1), Pt(13), bold=True,
                            color=IMPACT_BLUE, font=self.theme.heading_font,
                            space_after=0, line_spacing=1.0, first=True)
            used = self._prose(slide, text_left, y, text_w, budget, step,
                               max_pt=10.5, min_pt=9, label='Next step %d' % (index + 1))
            y += max(used, Inches(0.24)) + Inches(0.12)

        right_left = MARGIN + left_w + GUTTER
        right_w = CONTENT_W - left_w - GUTTER
        inner = right_w - 2 * PAD
        self._panel(slide, right_left, BODY_TOP, right_w, BODY_H)
        self._panel_label(slide, right_left + PAD, BODY_TOP + Inches(0.2), inner, 'Resources')
        # One text box with a paragraph a link, so each wraps as far as it needs
        # and the spacing between them stays even.
        top = BODY_TOP + Inches(0.52)
        box, used = None, 0
        for row in resources:
            url = row.get('url')
            label = (row.get('label') or '').strip()
            if not label and url:
                label = typeset.cite(url)[0]
            if not label:
                continue
            height = typeset.measure(label, int(inner), 9, 1.15) + int(Pt(7))
            if top + used + height > bottom:
                self._hold('Resource', '%s %s' % (label, url or ''))
                continue
            if box is None:
                box = add_textbox(slide, right_left + PAD, top, inner, bottom - top)
                p = box.text_frame.paragraphs[0]
            else:
                p = box.text_frame.add_paragraph()
            p.line_spacing = 1.15
            p.space_after = Pt(7)
            run = p.add_run()
            run.text = label
            set_run_font(run, Pt(9), False, IMPACT_BLUE if url else BLACK,
                         self.theme.body_font)
            if url:
                run.hyperlink.address = url
            used += height
        self._notes(slide, 'Agree the success metric and the readout date in writing.')

    def slide_one_pager(self):
        slide = self._page(('One page ', 'summary'),
                           kicker='Print this  ·  %s' % self.meta['competitor'])
        col_w = (CONTENT_W - GUTTER * 3) / 4
        inner = col_w - 2 * PAD

        def lead(text):
            clean, found = typeset.split_sources(text or '')
            self._sources.extend(found)
            first = typeset.sentences(clean)
            return first[0] if first else clean

        quadrants = (
            ('Why we win', [row.get('title', '') for row in self.card.get('our_advantages', [])]),
            ('Where they win', [lead(t) for t in self.card.get('their_strengths') or []]),
            ('Their gaps', [lead(t) for t in self.card.get('their_weaknesses') or []]),
            ('Top objections', [row.get('objection', '')
                                for row in self.card.get('objections') or []]),
        )
        strip_h = Inches(0.98)
        panel_h = BODY_H - strip_h - Inches(0.14)
        for index, (label, items) in enumerate(quadrants):
            left = MARGIN + index * (col_w + GUTTER)
            self._panel(slide, left, BODY_TOP, col_w, panel_h)
            self._panel_label(slide, left + PAD, BODY_TOP + Inches(0.14), inner, label,
                              size=Pt(7))
            entries = self._prep([item for item in items if item][:6], inner, 8,
                                 max_lines=3, label=label)
            rest = self._bullets(slide, left + PAD, BODY_TOP + Inches(0.38), inner,
                                 panel_h - Inches(0.5), entries or
                                 self._prep(['Add content.'], inner, 8),
                                 max_pt=9, min_pt=8, bullet_color=IMPACT_BLUE)
            for entry in rest:
                self._register(entry)

        strip_top = BODY_TOP + panel_h + Inches(0.14)
        self._panel(slide, MARGIN, strip_top, CONTENT_W, strip_h, fill=IMPACT_BLUE)
        self._panel_label(slide, MARGIN + PAD, strip_top + Inches(0.12), CONTENT_W - 2 * PAD,
                          'Say this first', color=mix(WHITE, IMPACT_BLUE, 0.4), size=Pt(7))
        line = (self.card.get('talk_track', {}).get('positioning')
                or self.meta.get('headline')
                or 'Lead with the outcome the buyer needs this season.')
        self._prose(slide, MARGIN + PAD, strip_top + Inches(0.34), CONTENT_W - 2 * PAD,
                    strip_h - Inches(0.44), line, max_pt=10.5, min_pt=9, color=WHITE,
                    label='Say this first')
        self._notes(slide, 'Print this slide. It is the card a seller carries into the room.')


def build_presentation(card: dict) -> Presentation:
    return BattlecardDeck(card).build()
