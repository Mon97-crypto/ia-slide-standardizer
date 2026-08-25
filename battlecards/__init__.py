"""Impact Analytics competitive battlecard builder.

Produces brand compliant PPTX decks that open unchanged in PowerPoint, Keynote
and Google Slides.
"""

from .builder import build_presentation
from .compat import audit
from .library import scaffold
from .schema import normalize, validate

__all__ = ['build_presentation', 'audit', 'scaffold', 'normalize', 'validate']
