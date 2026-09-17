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

from . import brand
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

    # ── presentation level ─────────────────────────────────────────────────────

    def _apply_theme_fonts(self):
        """Name the brand fonts in the theme as well as on every run.

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
        font_scheme = root.find('.//' + qn('a:fontScheme'))
        if font_scheme is None:
            return
        for tag, name in (('a:majorFont', self.theme.heading_font),
                          ('a:minorFont', self.theme.body_font)):
            node = font_scheme.find(qn(tag))
            if node is None:
                continue
            latin = node.find(qn('a:latin'))
            if latin is not None:
                latin.set('typeface', name)
        try:
            part._blob = etree.tostring(root, xml_declaration=True,
                                        encoding='UTF-8', standalone=True)
        except Exception:
            return

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

    def _default_kicker(self):
        return '%s battlecard  ·  %s' % (
            SOLUTION_LABELS.get(self.solution, ''), self.meta['competitor'])

    def _notes(self, slide, text):
        if not self.include_notes or not text:
            return
        slide.notes_slide.notes_text_frame.text = text

    def _page(self, title, kicker=None, dark=False, patterned=False):
        slide = self._slide(dark=dark, patterned=patterned)
        self._header(slide, title, kicker, dark=dark)
        self._footer(slide, dark=dark)
        return slide

    # ── reusable blocks ────────────────────────────────────────────────────────

    def _panel(self, slide, left, top, width, height, fill=None, border=None,
               shadow=True, accent=None, accent_height=None):
        """Draw a house card: white, rounded, soft shadow, no border, no stripe.

        The IA template sets a card apart with the shadow alone. `accent` is kept
        for the few places that genuinely need a coloured block rather than a
        card, and is drawn as a full fill, never as an edge stripe.
        """
        panel = add_rect(slide, left, top, width, height,
                         fill=fill or WHITE, line=border,
                         line_width=Pt(0.75), rounded=True)
        if shadow:
            add_soft_shadow(panel)
        return panel

    def _panel_label(self, slide, left, top, width, text, color=None, size=Pt(7.5)):
        box = add_textbox(slide, left, top, width, Inches(0.2))
        write_paragraph(box.text_frame, text.upper(), size, bold=True,
                        color=color or IMPACT_BLUE, font=self.theme.body_font,
                        space_after=0, line_spacing=1.0, first=True)
        return box

    def _pill(self, slide, left, top, avail_w, text, width=None, fill=None,
              size=Pt(10)):
        """Draw the house blue pill: solid Impact Blue, white bold text, centred.

        The template floats these over the top edge of a card, which is why the
        caller passes the available width and the pill centres itself inside it.
        """
        pill_w = width or avail_w
        pill_left = left + (avail_w - pill_w) / 2
        shape = add_rect(slide, pill_left, top, pill_w, Inches(0.26),
                         fill=fill or IMPACT_BLUE, rounded=True, radius=45000)
        tf = prepare_text_frame(shape, margin=Inches(0.06), anchor=MSO_ANCHOR.MIDDLE)
        write_paragraph(tf, text, size, bold=True, color=WHITE,
                        font=self.theme.body_font, align=PP_ALIGN.CENTER,
                        space_after=0, line_spacing=1.0, first=True)
        return shape

    def _bullets(self, slide, left, top, width, height, items, *, max_pt=12.0,
                 min_pt=8.0, color=BLACK, bullet_color=None, bullet='•'):
        if not items:
            return
        inner = int(width - 2 * Inches(0.16))
        size = fit_block_size(items, inner, int(height), max_pt, min_pt, gap_pt=5.0)
        box = add_textbox(slide, left, top, width, height)
        tf = box.text_frame
        tf.margin_left = Inches(0.0)
        tf.margin_right = Inches(0.0)
        for index, item in enumerate(items):
            write_paragraph(tf, item, size, color=color, font=self.theme.body_font,
                            bullet=bullet, space_after=4, line_spacing=1.2,
                            first=index == 0)
            if bullet_color is not None:
                brand.apply_bullet(tf.paragraphs[index], bullet, bullet_color)

    def _paragraph_block(self, slide, left, top, width, height, text, *,
                         max_pt=12.0, min_pt=8.0, color=BLACK, bold=False,
                         align=PP_ALIGN.LEFT, font=None):
        if not text:
            return
        size = fit_size(text, int(width), int(height), max_pt, min_pt)
        box = add_textbox(slide, left, top, width, height)
        write_paragraph(box.text_frame, text, size, bold=bold, color=color,
                        font=font or self.theme.body_font, align=align,
                        space_after=0, line_spacing=1.25, first=True)

    def _stat(self, slide, left, top, width, value, label, detail='', source=''):
        """Draw the house stat card.

        Measured from the template: a white outer card, an inner light blue panel
        holding the number in Impact Blue, then an italic label beneath it.
        """
        height = Inches(1.72)
        self._panel(slide, left, top, width, height)

        inner_w = width - 2 * PAD
        inner_h = Inches(0.62)
        inner = self._panel(slide, left + PAD, top + Inches(0.16), inner_w, inner_h,
                            fill=self.stat_tint, shadow=False)
        value_size = fit_size(value or '', int(inner_w), int(inner_h), 26, 12)
        tf = prepare_text_frame(inner, margin=Inches(0.06), anchor=MSO_ANCHOR.MIDDLE)
        write_paragraph(tf, value or 'Add stat', value_size, bold=True,
                        color=IMPACT_BLUE, font=self.theme.heading_font,
                        align=PP_ALIGN.CENTER, space_after=0, line_spacing=1.0,
                        first=True)

        label_top = top + Inches(0.86)
        label_h = Inches(0.46)
        label_size = fit_size(label or '', int(inner_w), int(label_h), 13, 8)
        label_box = add_textbox(slide, left + PAD, label_top, inner_w, label_h)
        write_paragraph(label_box.text_frame, label or '', label_size, color=BLACK,
                        font=self.theme.body_font, align=PP_ALIGN.CENTER,
                        space_after=0, line_spacing=1.1, first=True, italic=True)

        if detail:
            self._paragraph_block(slide, left + PAD, top + Inches(1.3), inner_w,
                                  Inches(0.26), detail, max_pt=8, min_pt=6.5,
                                  color=GRAY_3, align=PP_ALIGN.CENTER)
        if source:
            self._citation(slide, left + PAD, top + height - Inches(0.26),
                           inner_w, source)

    def _citation(self, slide, left, top, width, source):
        """Render a proof point source, whether a link or an internal citation."""
        if source.lower().startswith('http'):
            self._link(slide, left, top, width, 'Source', source)
            return
        box = add_textbox(slide, left, top, width, Inches(0.22))
        write_paragraph(box.text_frame, source, Pt(6), color=GRAY_3,
                        font=self.theme.body_font, align=PP_ALIGN.CENTER,
                        space_after=0, line_spacing=1.0, first=True)

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
               row_height=Inches(0.44), header_height=Inches(0.4), font_pt=10.0):
        """Draw a table with explicit fills, borders and fonts.

        The theme table style is removed so Google Slides never substitutes its
        own banding.
        """
        total = len(rows) + 1
        frame = slide.shapes.add_table(total, len(headers), int(left), int(top),
                                       int(width), int(header_height + row_height * len(rows)))
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
        for index in range(1, total):
            table.rows[index].height = int(row_height)

        for col, header in enumerate(headers):
            cell = table.cell(0, col)
            self._cell(cell, header, size=Pt(9.5), bold=True, color=WHITE,
                       fill=IMPACT_BLUE, align=PP_ALIGN.LEFT if col == 0 else PP_ALIGN.CENTER)

        for r, row in enumerate(rows, start=1):
            band = WHITE if r % 2 else OFF_WHITE
            for c, value in enumerate(row):
                text, color, bold, align = self._unpack_cell(value, c)
                cell = table.cell(r, c)
                self._cell(cell, text, size=Pt(font_pt), bold=bold, color=color,
                           fill=band, align=align)
        return table

    @staticmethod
    def _unpack_cell(value, column_index):
        if isinstance(value, dict):
            return (value.get('text', ''), value.get('color', BLACK),
                    value.get('bold', False),
                    value.get('align', PP_ALIGN.LEFT if column_index == 0 else PP_ALIGN.CENTER))
        return (str(value), BLACK, False,
                PP_ALIGN.LEFT if column_index == 0 else PP_ALIGN.CENTER)

    def _cell(self, cell, text, size, bold, color, fill, align):
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
        cell.margin_left = Inches(0.1)
        cell.margin_right = Inches(0.1)
        cell.margin_top = Inches(0.05)
        cell.margin_bottom = Inches(0.05)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = align
        p.line_spacing = 1.12
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
    # point of the slide.

    def slide_cover(self):
        slide = self._slide(dark=True, patterned=True)
        self._logo(slide, dark=True, height=Inches(0.3))

        kicker = 'Competitive battlecard  ·  %s' % SOLUTION_LABELS.get(self.solution, '')
        box = add_textbox(slide, MARGIN, Inches(1.22), CONTENT_W, Inches(0.22))
        write_paragraph(box.text_frame, kicker.upper(), Pt(8), bold=True, color=WHITE,
                        font=self.theme.body_font, space_after=0, line_spacing=1.0, first=True)

        title = self.meta['competitor']
        title_size = fit_size(title, int(CONTENT_W), int(Inches(1.05)), 40, 20)
        title_box = add_textbox(slide, MARGIN, Inches(1.52), CONTENT_W, Inches(1.05))
        write_paragraph(title_box.text_frame, title, title_size, bold=True, color=WHITE,
                        font=self.theme.heading_font, space_after=0, line_spacing=1.0, first=True)

        headline = self.meta.get('headline') or 'Know the rival. Lead with the outcome.'
        self._paragraph_block(slide, MARGIN, Inches(2.66), Inches(5.6), Inches(0.62),
                              headline, max_pt=12, min_pt=8.5,
                              color=mix(WHITE, IMPACT_BLUE, 0.12))

        facts = [
            ('Impact Analytics product', self.meta.get('ia_product') or 'Portfolio'),
            ('Their category', self.meta.get('competitor_category') or 'Add the category'),
            ('Prepared for', self.meta.get('audience')),
            ('Owner', self.meta.get('owner') or 'Add an owner'),
            ('Updated', self.meta.get('date')),
        ]
        top = Inches(3.62)
        col_w = (CONTENT_W - 4 * Inches(0.14)) / 5
        for index, (label, value) in enumerate(facts):
            left = MARGIN + index * (col_w + Inches(0.14))
            label_box = add_textbox(slide, left, top, col_w, Inches(0.18))
            write_paragraph(label_box.text_frame, label.upper(), Pt(6), bold=True,
                            color=mix(WHITE, IMPACT_BLUE, 0.4), font=self.theme.body_font,
                            space_after=0, line_spacing=1.0, first=True)
            self._paragraph_block(slide, left, top + Inches(0.18), col_w, Inches(0.46),
                                  value, max_pt=9, min_pt=6.5, color=WHITE)

        strip = add_textbox(slide, MARGIN, Inches(4.86), CONTENT_W, Inches(0.22))
        write_paragraph(strip.text_frame, self.meta['confidentiality'].upper(), Pt(7),
                        bold=True, color=mix(WHITE, IMPACT_BLUE, 0.4),
                        font=self.theme.body_font, space_after=0, line_spacing=1.0, first=True)
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
        self._bullets(slide, MARGIN + PAD, BODY_TOP + Inches(0.46), left_w - 2 * PAD,
                      BODY_H - Inches(0.66), items, max_pt=11, min_pt=8,
                      bullet_color=IMPACT_BLUE)

        right_left = MARGIN + left_w + GUTTER
        right_w = CONTENT_W - left_w - GUTTER
        self._panel(slide, right_left, BODY_TOP, right_w, BODY_H, fill=IMPACT_BLUE)
        self._panel_label(slide, right_left + PAD, BODY_TOP + Inches(0.2), right_w - 2 * PAD,
                          'Win theme', color=mix(WHITE, IMPACT_BLUE, 0.4))
        self._paragraph_block(slide, right_left + PAD, BODY_TOP + Inches(0.5),
                              right_w - 2 * PAD, BODY_H - Inches(0.72),
                              self.meta.get('win_theme') or 'Name the one reason this buyer switches.',
                              max_pt=12, min_pt=8, color=WHITE)
        self._notes(slide, 'Read this slide before the call, not during it.')

    def slide_snapshot(self):
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
        filled = [(label, value) for label, value in fields if value]
        moves = snapshot.get('recent_moves') or []
        customers = snapshot.get('notable_customers')
        if not filled and not moves and not customers:
            return

        slide = self._page(('Competitor ', 'snapshot'))
        left_w = Inches(5.75)
        self._panel(slide, MARGIN, BODY_TOP, left_w, BODY_H)
        self._panel_label(slide, MARGIN + PAD, BODY_TOP + Inches(0.2), left_w - 2 * PAD,
                          'Company facts')

        grid_top = BODY_TOP + Inches(0.5)
        cell_w = (left_w - 2 * PAD - Inches(0.2)) / 2
        cell_h = Inches(0.52)
        display = filled or [(label, 'Add detail') for label, _ in fields[:6]]
        rows_used = 0
        for index, (label, value) in enumerate(display[:8]):
            col, row = index % 2, index // 2
            rows_used = row + 1
            left = MARGIN + PAD + col * (cell_w + Inches(0.2))
            top = grid_top + row * cell_h
            label_box = add_textbox(slide, left, top, cell_w, Inches(0.16))
            write_paragraph(label_box.text_frame, label.upper(), Pt(6), bold=True,
                            color=GRAY_3, font=self.theme.body_font,
                            space_after=0, line_spacing=1.0, first=True)
            self._paragraph_block(slide, left, top + Inches(0.15), cell_w, Inches(0.34),
                                  value, max_pt=9.5, min_pt=7)

        if customers:
            top = grid_top + rows_used * cell_h + Inches(0.04)
            available = BODY_TOP + BODY_H - top - Inches(0.14)
            if available > Inches(0.3):
                label_box = add_textbox(slide, MARGIN + PAD, top, left_w - 2 * PAD, Inches(0.16))
                write_paragraph(label_box.text_frame, 'NAMED CUSTOMERS', Pt(6), bold=True,
                                color=GRAY_3, font=self.theme.body_font,
                                space_after=0, line_spacing=1.0, first=True)
                self._paragraph_block(slide, MARGIN + PAD, top + Inches(0.15),
                                      left_w - 2 * PAD, available - Inches(0.15),
                                      customers, max_pt=9, min_pt=7)

        right_left = MARGIN + left_w + GUTTER
        right_w = CONTENT_W - left_w - GUTTER
        self._panel(slide, right_left, BODY_TOP, right_w, BODY_H)
        self._panel_label(slide, right_left + PAD, BODY_TOP + Inches(0.2),
                          right_w - 2 * PAD, 'Recent moves')
        self._bullets(slide, right_left + PAD, BODY_TOP + Inches(0.46), right_w - 2 * PAD,
                      BODY_H - Inches(0.66),
                      moves or ['Add funding, product or leadership news, with a source link.'],
                      max_pt=9.5, min_pt=7, bullet_color=self.theme.accent)
        self._notes(slide, 'Every fact on this slide needs a dated source. Refresh it each quarter.')

    def slide_positioning(self):
        positioning = self.card.get('positioning', {})
        if not any(positioning.values()):
            return
        slide = self._page(('Positioning ', 'face off'))
        col_w = (CONTENT_W - GUTTER) / 2
        panel_h = BODY_H - Inches(1.02)

        self._panel(slide, MARGIN, BODY_TOP, col_w, panel_h)
        self._panel_label(slide, MARGIN + PAD, BODY_TOP + Inches(0.2), col_w - 2 * PAD,
                          'They say', color=GRAY_3)
        self._paragraph_block(slide, MARGIN + PAD, BODY_TOP + Inches(0.48), col_w - 2 * PAD,
                              panel_h - Inches(0.68),
                              positioning.get('their_claim') or 'Paste their positioning line.',
                              max_pt=12, min_pt=8)

        right = MARGIN + col_w + GUTTER
        self._panel(slide, right, BODY_TOP, col_w, panel_h, fill=IMPACT_BLUE)
        self._panel_label(slide, right + PAD, BODY_TOP + Inches(0.2), col_w - 2 * PAD,
                          'We say', color=mix(WHITE, IMPACT_BLUE, 0.4))
        self._paragraph_block(slide, right + PAD, BODY_TOP + Inches(0.48), col_w - 2 * PAD,
                              panel_h - Inches(0.68),
                              positioning.get('our_claim') or 'Write the Impact Analytics line.',
                              max_pt=12, min_pt=8, color=WHITE)

        wedge_top = BODY_TOP + panel_h + Inches(0.14)
        wedge_h = BODY_H - panel_h - Inches(0.14)
        self._panel(slide, MARGIN, wedge_top, CONTENT_W, wedge_h)
        self._panel_label(slide, MARGIN + PAD, wedge_top + Inches(0.16), CONTENT_W - 2 * PAD,
                          'The wedge')
        self._paragraph_block(slide, MARGIN + PAD, wedge_top + Inches(0.42),
                              CONTENT_W - 2 * PAD, wedge_h - Inches(0.56),
                              positioning.get('wedge') or 'Name the gap this buyer feels weekly.',
                              max_pt=11, min_pt=8)
        self._notes(slide, 'Say the wedge in the buyer own words. Quote them back.')

    def slide_strengths_weaknesses(self):
        strengths = self.card.get('their_strengths') or []
        weaknesses = self.card.get('their_weaknesses') or []
        if not strengths and not weaknesses:
            return
        slide = self._page(('Where they win, ', 'where they fall short'))
        col_w = (CONTENT_W - GUTTER) / 2
        for index, (label, items) in enumerate((
                ('Where %s wins' % self.meta['competitor'], strengths),
                ('Where %s falls short' % self.meta['competitor'], weaknesses))):
            left = MARGIN + index * (col_w + GUTTER)
            self._panel(slide, left, BODY_TOP, col_w, BODY_H)
            self._panel_label(slide, left + PAD, BODY_TOP + Inches(0.2), col_w - 2 * PAD,
                              label, color=GRAY_3 if index == 0 else IMPACT_BLUE)
            self._bullets(slide, left + PAD, BODY_TOP + Inches(0.5), col_w - 2 * PAD,
                          BODY_H - Inches(0.7),
                          items or ['Add at least three points.'],
                          max_pt=11, min_pt=8,
                          bullet_color=GRAY_3 if index == 0 else IMPACT_BLUE)
        self._notes(slide, 'An honest read of their strengths buys credibility for the rest.')

    def slide_why_we_win(self):
        advantages = self.card.get('our_advantages') or []
        if not advantages:
            return
        for group in chunk(advantages, 3):
            slide = self._page(('Why Impact Analytics ', 'wins'))
            count = len(group)
            col_w = (CONTENT_W - GUTTER * (count - 1)) / count
            for index, row in enumerate(group):
                left = MARGIN + index * (col_w + GUTTER)
                self._panel(slide, left, BODY_TOP, col_w, BODY_H)
                self._pill(slide, left + PAD, BODY_TOP - Inches(0.1),
                           col_w - 2 * PAD, '0%d' % (index + 1), width=Inches(0.52))
                self._paragraph_block(slide, left + PAD, BODY_TOP + Inches(0.34),
                                      col_w - 2 * PAD, Inches(0.6),
                                      row.get('title', ''), max_pt=13, min_pt=9.5,
                                      bold=True, font=self.theme.heading_font)
                proof = row.get('proof')
                detail_h = BODY_H - Inches(1.78) if proof else BODY_H - Inches(1.1)
                self._paragraph_block(slide, left + PAD, BODY_TOP + Inches(0.98),
                                      col_w - 2 * PAD, detail_h,
                                      row.get('detail', ''), max_pt=10, min_pt=7)
                if proof:
                    proof_top = BODY_TOP + BODY_H - Inches(0.8)
                    label = add_textbox(slide, left + PAD, proof_top,
                                        col_w - 2 * PAD, Inches(0.16))
                    write_paragraph(label.text_frame, 'PROOF', Pt(6), bold=True,
                                    color=GRAY_3, font=self.theme.body_font,
                                    space_after=0, line_spacing=1.0, first=True)
                    self._paragraph_block(slide, left + PAD, proof_top + Inches(0.16),
                                          col_w - 2 * PAD, Inches(0.56), proof,
                                          max_pt=8.5, min_pt=6.5, color=IMPACT_BLUE)
            self._notes(slide, 'Lead with the outcome. Name the product second.')

    def slide_comparison(self):
        rows = self.card.get('comparison') or []
        if not rows:
            return
        pages = chunk(rows, 7)
        for index, group in enumerate(pages):
            emphasis = self.meta['competitor']
            if len(pages) > 1:
                emphasis = '%s (%d of %d)' % (emphasis, index + 1, len(pages))
            slide = self._page(('Head to head: ', emphasis))
            headers = ['Capability', 'Impact Analytics', self.meta['competitor'], 'What to say']
            table_rows = []
            for row in group:
                table_rows.append([
                    {'text': row.get('capability', ''), 'bold': True, 'align': PP_ALIGN.LEFT},
                    self._rating_cell(row.get('ia')),
                    self._rating_cell(row.get('competitor')),
                    {'text': row.get('note', ''), 'align': PP_ALIGN.LEFT, 'color': BLACK},
                ])
            header_h = Inches(0.3)
            row_height = min(Inches(0.42), max(Inches(0.26),
                                               (BODY_H - header_h - Inches(0.3)) / max(1, len(group))))
            self._table(slide, MARGIN, BODY_TOP, CONTENT_W, headers, table_rows,
                        col_ratios=[0.30, 0.14, 0.14, 0.42],
                        row_height=row_height, header_height=header_h, font_pt=8)
            legend_top = BODY_TOP + header_h + row_height * len(group) + Inches(0.1)
            if legend_top < FOOTER_TEXT_Y - Inches(0.24):
                self._legend(slide, MARGIN, legend_top)
            self._notes(slide, 'Show this only when the buyer asks for a direct comparison. '
                               'Defend every row with evidence.')

    def _rating_cell(self, rating):
        key = rating if rating in RATING_LABELS else 'unknown'
        return {'text': RATING_LABELS[key], 'color': RATING_COLORS[key],
                'bold': key == 'strong', 'align': PP_ALIGN.CENTER}

    def _legend(self, slide, left, top):
        box = add_textbox(slide, left, top, CONTENT_W, Inches(0.2))
        p = box.text_frame.paragraphs[0]
        p.line_spacing = 1.0
        for index, key in enumerate(('strong', 'partial', 'none', 'unknown')):
            run = p.add_run()
            run.text = ('   ' if index else '') + RATING_LABELS[key]
            set_run_font(run, Pt(7), True, RATING_COLORS[key], self.theme.body_font)
            gloss = p.add_run()
            gloss.text = {'strong': ' ships today', 'partial': ' partial coverage',
                          'none': ' not available', 'unknown': ' needs research'}[key]
            set_run_font(gloss, Pt(7), False, GRAY_3, self.theme.body_font)

    def slide_objections(self):
        rows = self.card.get('objections') or []
        if not rows:
            return
        for group in chunk(rows, 2):
            slide = self._page(('Objection ', 'handling'))
            count = len(group)
            row_h = (BODY_H - GUTTER * (count - 1)) / count
            for index, row in enumerate(group):
                top = BODY_TOP + index * (row_h + GUTTER)
                self._panel(slide, MARGIN, top, CONTENT_W, row_h)
                col_w = (CONTENT_W - 2 * PAD) / 3
                blocks = (
                    ('They say', row.get('objection', ''), GRAY_3, BLACK),
                    ('We say', row.get('response', ''), IMPACT_BLUE, BLACK),
                    ('Proof', row.get('proof', ''), GRAY_3, IMPACT_BLUE),
                )
                for col, (label, text, label_color, text_color) in enumerate(blocks):
                    left = MARGIN + PAD + col * col_w
                    inner_w = col_w - Inches(0.16)
                    self._panel_label(slide, left, top + Inches(0.12), inner_w, label,
                                      color=label_color, size=Pt(6.5))
                    self._paragraph_block(slide, left, top + Inches(0.32), inner_w,
                                          row_h - Inches(0.46), text,
                                          max_pt=9.5, min_pt=7, color=text_color)
            self._notes(slide, 'Answer the objection once, then return to the outcome.')

    def slide_landmines(self):
        rows = self.card.get('landmines') or []
        if not rows:
            return
        for group in chunk(rows, 3):
            slide = self._page(('Landmines ', 'to set'))
            count = len(group)
            col_w = (CONTENT_W - GUTTER * (count - 1)) / count
            question_h = Inches(1.0)
            why_top = BODY_TOP + question_h + Inches(0.16)
            why_h = Inches(0.82)
            listen_top = why_top + why_h + Inches(0.12)
            for index, row in enumerate(group):
                left = MARGIN + index * (col_w + GUTTER)
                self._panel(slide, left, BODY_TOP, col_w, BODY_H)
                self._panel_label(slide, left + PAD, BODY_TOP + Inches(0.16), col_w - 2 * PAD,
                                  'Ask this', size=Pt(6.5))
                self._paragraph_block(slide, left + PAD, BODY_TOP + Inches(0.36),
                                      col_w - 2 * PAD, question_h - Inches(0.2),
                                      row.get('question', ''), max_pt=11, min_pt=8,
                                      bold=True, font=self.theme.heading_font)
                self._panel_label(slide, left + PAD, why_top, col_w - 2 * PAD,
                                  'Why it lands', color=GRAY_3, size=Pt(6.5))
                self._paragraph_block(slide, left + PAD, why_top + Inches(0.18),
                                      col_w - 2 * PAD, why_h - Inches(0.18),
                                      row.get('why', ''), max_pt=9.5, min_pt=7)
                self._panel_label(slide, left + PAD, listen_top, col_w - 2 * PAD,
                                  'Listen for', color=GRAY_3, size=Pt(6.5))
                self._paragraph_block(slide, left + PAD, listen_top + Inches(0.18),
                                      col_w - 2 * PAD,
                                      BODY_TOP + BODY_H - listen_top - Inches(0.3),
                                      row.get('listen_for', ''), max_pt=9.5, min_pt=7,
                                      color=IMPACT_BLUE)
            self._notes(slide, 'Set one landmine per call. More than one sounds rehearsed.')

    def slide_discovery(self):
        rows = self.card.get('discovery') or []
        if not rows:
            return
        for group in chunk(rows, 3):
            slide = self._page(('Discovery ', 'questions'))
            count = len(group)
            col_w = (CONTENT_W - GUTTER * (count - 1)) / count
            for index, row in enumerate(group):
                left = MARGIN + index * (col_w + GUTTER)
                self._panel(slide, left, BODY_TOP, col_w, BODY_H)
                self._paragraph_block(slide, left + PAD, BODY_TOP + Inches(0.18),
                                      col_w - 2 * PAD, Inches(0.5),
                                      row.get('theme', ''), max_pt=12, min_pt=9,
                                      bold=True, font=self.theme.heading_font)
                self._bullets(slide, left + PAD, BODY_TOP + Inches(0.78), col_w - 2 * PAD,
                              BODY_H - Inches(0.98), row.get('questions') or [],
                              max_pt=10, min_pt=7, bullet_color=IMPACT_BLUE)
            self._notes(slide, 'Run discovery before any slide goes on the screen.')

    def slide_proof_points(self):
        rows = self.card.get('proof_points') or []
        if not rows:
            return
        for group in chunk(rows, 4):
            slide = self._page(('Proof ', 'points'))
            count = len(group)
            col_w = (CONTENT_W - GUTTER * (count - 1)) / count
            for index, row in enumerate(group):
                left = MARGIN + index * (col_w + GUTTER)
                self._stat(slide, left, BODY_TOP, col_w, row.get('stat', ''),
                           row.get('label', ''), row.get('detail', ''), row.get('source', ''))
            note_top = BODY_TOP + Inches(1.86)
            note_h = BODY_H - Inches(1.86)
            if note_h > Inches(0.6):
                self._panel(slide, MARGIN, note_top, CONTENT_W, note_h)
                self._panel_label(slide, MARGIN + PAD, note_top + Inches(0.14),
                                  CONTENT_W - 2 * PAD, 'How to use these numbers')
                self._bullets(slide, MARGIN + PAD, note_top + Inches(0.38), CONTENT_W - 2 * PAD,
                              note_h - Inches(0.52), [
                                  'Quote the number, then name the customer situation behind it.',
                                  'Carry the source. A stat you cannot attribute loses the room.',
                                  'Use results from 2025 or later. Retire anything older.',
                              ], max_pt=10, min_pt=7.5, bullet_color=IMPACT_BLUE)
            self._notes(slide, 'Never quote a result you cannot source on request.')

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
        cols = 2
        rows = math.ceil(len(blocks) / cols)
        col_w = (CONTENT_W - GUTTER) / cols
        row_h = (BODY_H - GUTTER * (rows - 1)) / rows
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
            self._paragraph_block(slide, left + PAD, top + Inches(0.36), col_w - 2 * PAD,
                                  row_h - Inches(0.5), text, max_pt=10.5, min_pt=7.5,
                                  color=WHITE if highlight else BLACK)
        self._notes(slide, 'Say it out loud twice before the call. Cut any sentence that does not land.')

    def slide_dos_donts(self):
        dos = self.card.get('dos') or []
        donts = self.card.get('donts') or []
        if not dos and not donts:
            return
        slide = self._page(('Do ', 'and do not'))
        col_w = (CONTENT_W - GUTTER) / 2
        for index, (label, items, color) in enumerate((
                ('Do', dos, IMPACT_BLUE),
                ('Do not', donts, GRAY_3))):
            left = MARGIN + index * (col_w + GUTTER)
            self._panel(slide, left, BODY_TOP, col_w, BODY_H)
            self._panel_label(slide, left + PAD, BODY_TOP + Inches(0.2), col_w - 2 * PAD,
                              label, color=color)
            self._bullets(slide, left + PAD, BODY_TOP + Inches(0.5), col_w - 2 * PAD,
                          BODY_H - Inches(0.7), items or ['Add guidance.'],
                          max_pt=11, min_pt=8, bullet_color=color)
        self._notes(slide, 'These rules keep the conversation about value, not about the rival.')

    def slide_pricing(self):
        pricing = self.card.get('pricing', {})
        notes = pricing.get('notes') or []
        if not any((pricing.get('ia_model'), pricing.get('competitor_model'), notes)):
            return
        slide = self._page(('Pricing and ', 'packaging'))
        col_w = (CONTENT_W - GUTTER) / 2
        panel_h = BODY_H - Inches(1.32)
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
            self._paragraph_block(slide, left + PAD, BODY_TOP + Inches(0.42), col_w - 2 * PAD,
                                  panel_h - Inches(0.58), text or 'Add detail.',
                                  max_pt=10.5, min_pt=7.5, color=ink)
        note_top = BODY_TOP + panel_h + Inches(0.14)
        note_h = BODY_H - panel_h - Inches(0.14)
        self._panel(slide, MARGIN, note_top, CONTENT_W, note_h)
        self._panel_label(slide, MARGIN + PAD, note_top + Inches(0.13), CONTENT_W - 2 * PAD,
                          'Ground rules', color=GRAY_3, size=Pt(7))
        self._bullets(slide, MARGIN + PAD, note_top + Inches(0.33), CONTENT_W - 2 * PAD,
                      note_h - Inches(0.46),
                      notes or ['Record only what the buyer states or the vendor publishes.'],
                      max_pt=9, min_pt=7, bullet_color=GRAY_3)
        self._notes(slide, 'Never quote a rival price you cannot source.')

    def slide_next_steps(self):
        steps = self.card.get('next_steps') or []
        resources = self.card.get('resources') or []
        if not steps and not resources:
            return
        slide = self._page(('Next steps ', 'and resources'))
        left_w = Inches(5.75)
        self._panel(slide, MARGIN, BODY_TOP, left_w, BODY_H)
        self._panel_label(slide, MARGIN + PAD, BODY_TOP + Inches(0.2), left_w - 2 * PAD,
                          'Move the deal forward')
        step_top = BODY_TOP + Inches(0.52)
        visible = steps[:5]
        step_h = (BODY_H - Inches(0.72)) / max(1, len(visible))
        for index, step in enumerate(visible):
            top = step_top + index * step_h
            marker = add_textbox(slide, MARGIN + PAD, top, Inches(0.28), Inches(0.28))
            write_paragraph(marker.text_frame, str(index + 1), Pt(12), bold=True,
                            color=self.theme.accent, font=self.theme.heading_font,
                            space_after=0, line_spacing=1.0, first=True)
            self._paragraph_block(slide, MARGIN + PAD + Inches(0.32), top,
                                  left_w - 2 * PAD - Inches(0.32), step_h - Inches(0.08),
                                  step, max_pt=10.5, min_pt=7.5)

        right_left = MARGIN + left_w + GUTTER
        right_w = CONTENT_W - left_w - GUTTER
        self._panel(slide, right_left, BODY_TOP, right_w, BODY_H)
        self._panel_label(slide, right_left + PAD, BODY_TOP + Inches(0.2), right_w - 2 * PAD,
                          'Resources')
        top = BODY_TOP + Inches(0.5)
        for row in resources[:7]:
            label = row.get('label') or row.get('url')
            url = row.get('url')
            box = add_textbox(slide, right_left + PAD, top, right_w - 2 * PAD, Inches(0.24))
            p = box.text_frame.paragraphs[0]
            p.line_spacing = 1.1
            run = p.add_run()
            run.text = label
            set_run_font(run, Pt(9.5), False, IMPACT_BLUE if url else BLACK,
                         self.theme.body_font)
            if url:
                run.hyperlink.address = url
            top += Inches(0.26)
        owner = self.meta.get('owner')
        if owner:
            self._paragraph_block(slide, right_left + PAD, BODY_TOP + BODY_H - Inches(0.42),
                                  right_w - 2 * PAD, Inches(0.3),
                                  'Card owner: %s' % owner, max_pt=8, min_pt=6.5, color=GRAY_3)
        self._notes(slide, 'Agree the success metric and the readout date in writing.')

    def slide_one_pager(self):
        slide = self._page(('One page ', 'summary'),
                           kicker='Print this  ·  %s' % self.meta['competitor'])
        col_w = (CONTENT_W - GUTTER * 3) / 4
        quadrants = (
            ('Why we win', [row.get('title', '') for row in self.card.get('our_advantages', [])][:4]),
            ('Where they win', (self.card.get('their_strengths') or [])[:4]),
            ('Their gaps', (self.card.get('their_weaknesses') or [])[:4]),
            ('Top objections', self._objection_pairs()),
        )
        panel_h = BODY_H - Inches(1.06)
        for index, (label, items) in enumerate(quadrants):
            left = MARGIN + index * (col_w + GUTTER)
            self._panel(slide, left, BODY_TOP, col_w, panel_h)
            self._panel_label(slide, left + PAD, BODY_TOP + Inches(0.14), col_w - 2 * PAD,
                              label, size=Pt(7))
            self._bullets(slide, left + PAD, BODY_TOP + Inches(0.36), col_w - 2 * PAD,
                          panel_h - Inches(0.5),
                          [item for item in items if item] or ['Add content.'],
                          max_pt=8.5, min_pt=6.5, bullet_color=IMPACT_BLUE)

        strip_top = BODY_TOP + panel_h + Inches(0.14)
        strip_h = BODY_H - panel_h - Inches(0.14)
        self._panel(slide, MARGIN, strip_top, CONTENT_W, strip_h, fill=IMPACT_BLUE)
        self._panel_label(slide, MARGIN + PAD, strip_top + Inches(0.12), CONTENT_W - 2 * PAD,
                          'Say this first', color=mix(WHITE, IMPACT_BLUE, 0.4), size=Pt(7))
        line = (self.card.get('talk_track', {}).get('positioning')
                or self.meta.get('headline')
                or 'Lead with the outcome the buyer needs this season.')
        self._paragraph_block(slide, MARGIN + PAD, strip_top + Inches(0.32),
                              CONTENT_W - 2 * PAD, strip_h - Inches(0.44), line,
                              max_pt=11, min_pt=7.5, color=WHITE)
        self._notes(slide, 'Print this slide. It is the card a seller carries into the room.')

    def _objection_pairs(self):
        """Compact objection and answer pairs for the printable summary."""
        pairs = []
        for row in (self.card.get('objections') or [])[:2]:
            if row.get('objection'):
                pairs.append('They say: %s' % row['objection'])
            if row.get('response'):
                pairs.append('We say: %s' % row['response'])
        return pairs


def build_presentation(card: dict) -> Presentation:
    return BattlecardDeck(card).build()
