"""Google Slides compatibility checks for a generated PPTX.

Google Slides imports a subset of OOXML. The constructs below either render
differently or get dropped, so the builder avoids them and this module proves it.
Run `audit(path)` on any deck to get a list of findings.
"""

from __future__ import annotations

import os
import re
import zipfile

# Google Slides caps an uploaded presentation at 100 MB and 400 slides.
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_SLIDES = 400
# Slides that Google renders well stay under a few hundred shapes.
MAX_SHAPES_PER_SLIDE = 220

NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
NS_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'

UNSUPPORTED = [
    ('a:sp3d', 'Three dimensional shape formatting is dropped on import.'),
    ('a:scene3d', 'Three dimensional scene formatting is dropped on import.'),
    ('a:effectLst/a:reflection', 'Reflection effects are dropped on import.'),
    ('a:effectLst/a:glow', 'Glow effects are dropped on import.'),
    ('a:effectLst/a:softEdge', 'Soft edges are dropped on import.'),
    ('p:transition', 'Transitions are replaced by the Google Slides defaults.'),
    ('a:custGeom', 'Custom geometry can shift. Prefer preset shapes.'),
    ('a:blipFill/a:tile', 'Tiled picture fills are flattened.'),
]

SLIDE_RE = re.compile(r'^ppt/slides/slide\d+\.xml$')


def audit(path: str) -> dict:
    """Return findings for one PPTX file."""
    findings = []
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        findings.append(_finding('file_size', 'error',
                                 'The file is %.1f MB. Google Slides rejects uploads over 100 MB.'
                                 % (size / 1048576.0)))

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        slides = sorted(name for name in names if SLIDE_RE.match(name))
        if len(slides) > MAX_SLIDES:
            findings.append(_finding('slide_count', 'error',
                                     'The deck has %d slides. Google Slides caps a file at 400.'
                                     % len(slides)))
        for name in slides:
            xml = archive.read(name).decode('utf-8', 'replace')
            findings.extend(_audit_slide(name, xml))

        if 'ppt/theme/theme1.xml' in names:
            theme = archive.read('ppt/theme/theme1.xml').decode('utf-8', 'replace')
            if 'Inter Tight' not in theme:
                findings.append(_finding('theme_font', 'warning',
                                         'The theme does not name a brand font. New text boxes will '
                                         'fall back to the Google Slides default.'))

    return {
        'ok': not any(item['level'] == 'error' for item in findings),
        'slide_count': len(slides),
        'file_bytes': size,
        'findings': findings,
    }


def _audit_slide(name: str, xml: str) -> list:
    findings = []
    label = name.rsplit('/', 1)[-1]

    for tag, message in UNSUPPORTED:
        needle = tag.split('/')[-1]
        if '<%s' % needle in xml:
            findings.append(_finding('unsupported_feature', 'warning',
                                     '%s uses %s. %s' % (label, needle, message)))

    if 'normAutofit' in xml and 'fontScale' in xml:
        findings.append(_finding('autofit', 'warning',
                                 '%s relies on PowerPoint shrink on overflow. Google Slides ignores '
                                 'the font scale, so the text will overflow.' % label))

    if '<a:latin' not in xml and '<a:t>' in xml:
        findings.append(_finding('run_font', 'warning',
                                 '%s has text with no explicit typeface. Google Slides may '
                                 'substitute a different font.' % label))

    shape_count = xml.count('<p:sp>') + xml.count('<p:pic>') + xml.count('<p:graphicFrame>')
    if shape_count > MAX_SHAPES_PER_SLIDE:
        findings.append(_finding('shape_count', 'warning',
                                 '%s holds %d shapes. Dense slides slow the Google Slides editor.'
                                 % (label, shape_count)))

    for match in re.finditer(r'r:id="[^"]*"[^>]*>|<a:hlinkClick', xml):
        pass
    if 'javascript:' in xml.lower():
        findings.append(_finding('link_scheme', 'error',
                                 '%s contains a script link. Remove it.' % label))

    return findings


def _finding(rule, level, message):
    return {'rule': rule, 'level': level, 'message': message}
