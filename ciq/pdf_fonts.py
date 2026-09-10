"""A Unicode font for PDFs built from text nobody on this side wrote.

The battlecard PDF is rendered from copy the model produced, so a small
substitution table covers it. A captured web page is different: it can carry
accented names, Greek, Cyrillic, curly quotes, arrows, currency marks or
emoji, and ReportLab's built-in fonts cover Latin-1 only. Anything outside it
draws as a solid black box rather than raising, so a page would come back
looking corrupted with no error anywhere.

DejaVu covers Latin, Greek and Cyrillic and is a one megabyte apt package, so
the Dockerfile installs it. When it is missing the module falls back through
ReportLab's bundled Vera to the built-in Helvetica, and reports what it got so
the caller can sanitise to match. Coverage is read from the font's own cmap
rather than assumed, so the sanitiser can never be wrong about it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Each family gives a directory and the faces to look for in it. Regular and
# bold are required; the oblique faces ship in a separate package on Debian, so
# they are optional and fall back to the upright face rather than failing the
# whole family over a nicety.
_FAMILIES = [
    ("DejaVuSans", "/usr/share/fonts/truetype/dejavu"),
    ("DejaVuSans", "/usr/share/fonts/dejavu"),
    ("DejaVuSans", "/usr/local/share/fonts/dejavu"),
]
_FACES = {"": "DejaVuSans.ttf", "-Bold": "DejaVuSans-Bold.ttf",
          "-Italic": "DejaVuSans-Oblique.ttf",
          "-BoldItalic": "DejaVuSans-BoldOblique.ttf"}

# Equivalents for characters the chosen font cannot draw. Losing a character
# outright is worse than printing something close to it.
_FOLD = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "′": "'", "″": '"',
    "–": "-", "—": " - ", "―": "-", "−": "-",
    "…": "...", "•": "-", "·": "-", "●": "-", "▪": "-",
    "→": "->", "←": "<-", "⇒": "=>", "≥": ">=", "≤": "<=",
    "×": "x", "✓": "y", "✗": "n", " ": " ", "​": "",
    " ": " ", " ": " ", "﻿": "", "­": "",
    "™": "(TM)", "®": "(R)", "©": "(c)", "‹": "<", "›": ">",
}


@dataclass
class Fonts:
    """The font names to render with, and what they can actually draw."""

    regular: str = "Helvetica"
    bold: str = "Helvetica-Bold"
    italic: str = "Helvetica-Oblique"
    bold_italic: str = "Helvetica-BoldOblique"
    unicode: bool = False
    coverage: frozenset = field(default_factory=frozenset)

    def clean(self, text) -> str:
        """Return text this font can draw, XML-escaped for a Paragraph.

        Characters outside the font are folded to an equivalent where one
        exists and dropped otherwise, because the alternative is a black box
        on the page that looks like a rendering fault.
        """
        value = "" if text is None else str(text)
        out = []
        for char in value:
            if self._covers(char):
                out.append(char)
                continue
            replacement = _FOLD.get(char)
            if replacement is None and char.isspace():
                replacement = " "
            if replacement:
                out.append("".join(c for c in replacement if self._covers(c)))
        joined = "".join(out)
        return (joined.replace("&", "&amp;")
                      .replace("<", "&lt;").replace(">", "&gt;"))

    def _covers(self, char: str) -> bool:
        if self.coverage:
            return ord(char) in self.coverage
        try:                                  # built-in fonts are Latin-1 only
            char.encode("latin-1")
            return True
        except UnicodeEncodeError:
            return False


_cached: Fonts | None = None


def load() -> Fonts:
    """Register the best available family once, and describe it."""
    global _cached
    if _cached is not None:
        return _cached
    _cached = _register()
    return _cached


def _register() -> Fonts:
    for name, directory in _FAMILIES:
        paths = {suffix: os.path.join(directory, filename)
                 for suffix, filename in _FACES.items()}
        if not all(os.path.exists(paths[suffix]) for suffix in ("", "-Bold")):
            continue
        try:
            coverage = None
            registered = []
            for suffix in ("", "-Bold", "-Italic", "-BoldItalic"):
                if not os.path.exists(paths[suffix]):
                    continue
                font = TTFont(name + suffix, paths[suffix])
                pdfmetrics.registerFont(font)
                registered.append(suffix)
                if suffix == "":
                    coverage = frozenset(font.face.charToGlyph)
            italic = name + ("-Italic" if "-Italic" in registered else "")
            bold_italic = name + ("-BoldItalic" if "-BoldItalic" in registered
                                  else "-Bold")
            pdfmetrics.registerFontFamily(
                name, normal=name, bold=f"{name}-Bold",
                italic=italic, boldItalic=bold_italic)
            return Fonts(regular=name, bold=f"{name}-Bold", italic=italic,
                         bold_italic=bold_italic, unicode=True,
                         coverage=coverage or frozenset())
        except Exception:                     # a broken font must not stop a render
            continue
    return Fonts()
