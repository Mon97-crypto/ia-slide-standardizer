"""Brand pattern assets generated once and cached on disk.

The brand guide calls for a thin line grid at 10 percent opacity with a grain
texture over solid Impact Blue, and it requires the pattern to bleed off every
edge. Generating the overlay as a single transparent PNG keeps the slide to one
picture instead of hundreds of hairline shapes, which is what Google Slides
handles best.
"""

from __future__ import annotations

import os
import random

CACHE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'static', 'images', 'generated'))

GRID_OVERLAY = os.path.join(CACHE_DIR, 'ia_grid_overlay.png')
DOT_OVERLAY = os.path.join(CACHE_DIR, 'ia_dot_overlay.png')

WIDTH, HEIGHT = 1280, 720
GRID_STEP = 40
GRID_ALPHA = 26     # 10 percent of 255
GRAIN_ALPHA = 14    # visible on inspection, never loud
DOT_ALPHA = 38


def _cached(path):
    return path if os.path.exists(path) else None


def grid_overlay() -> str:
    """White grid lines plus grain, transparent elsewhere. Bleeds off all edges."""
    existing = _cached(GRID_OVERLAY)
    if existing:
        return existing
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return ''
    os.makedirs(CACHE_DIR, exist_ok=True)
    image = Image.new('RGBA', (WIDTH, HEIGHT), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    # Offset the start so no grid line lands exactly on an edge.
    for x in range(-GRID_STEP // 2, WIDTH + GRID_STEP, GRID_STEP):
        draw.line([(x, 0), (x, HEIGHT)], fill=(255, 255, 255, GRID_ALPHA), width=1)
    for y in range(-GRID_STEP // 2, HEIGHT + GRID_STEP, GRID_STEP):
        draw.line([(0, y), (WIDTH, y)], fill=(255, 255, 255, GRID_ALPHA), width=1)
    _apply_grain(image)
    image.save(GRID_OVERLAY, 'PNG', optimize=True)
    return GRID_OVERLAY


def dot_overlay() -> str:
    """Secondary dot pattern. Never combined with the grid in one composition."""
    existing = _cached(DOT_OVERLAY)
    if existing:
        return existing
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return ''
    os.makedirs(CACHE_DIR, exist_ok=True)
    image = Image.new('RGBA', (WIDTH, HEIGHT), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    step = 32
    for y in range(-step // 2, HEIGHT + step, step):
        for x in range(-step // 2, WIDTH + step, step):
            draw.ellipse([x, y, x + 2, y + 2], fill=(255, 255, 255, DOT_ALPHA))
    _apply_grain(image)
    image.save(DOT_OVERLAY, 'PNG', optimize=True)
    return DOT_OVERLAY


def _apply_grain(image):
    """Sparse white speckle. Deterministic, so the asset is reproducible."""
    rng = random.Random(2026)
    pixels = image.load()
    count = (image.width * image.height) // 22
    for _ in range(count):
        x = rng.randrange(image.width)
        y = rng.randrange(image.height)
        r, g, b, a = pixels[x, y]
        if a == 0:
            pixels[x, y] = (255, 255, 255, GRAIN_ALPHA)
