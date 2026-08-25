# IA Slide Standardizer

Two tools for Impact Analytics slide work, served from one Flask app.

1. **Slide Standardizer** at `/` converts an existing PPTX or a screenshot into the IA template.
2. **Battlecard Builder** at `/battlecard` builds a competitive battlecard deck from structured input.

Both follow the Impact Analytics brand guide. Every deck the battlecard builder writes opens
unchanged in PowerPoint, Keynote and Google Slides.

## Running it

```bash
pip install -r requirements.txt
python3 app.py            # http://127.0.0.1:5000
python3 -m pytest tests -q
```

Docker and Render configuration already exist in `Dockerfile` and `render.yaml`.

## Battlecard Builder

### What it produces

A battlecard deck of up to 16 sections. Long sections paginate on their own, so seven
objections become three slides without any manual work.

| Section | Slide |
|---|---|
| `cover` | Title card on Impact Blue with the grid pattern and the white logo |
| `how_to_use` | Working rules plus the win theme |
| `snapshot` | Company facts grid and recent moves |
| `positioning` | Their claim, our claim, and the wedge between them |
| `strengths_weaknesses` | An honest read of both sides |
| `why_we_win` | Numbered advantage cards, each with a proof line |
| `comparison` | Head to head capability matrix with a rating legend |
| `objections` | They say, we say, proof |
| `landmines` | Trap questions with why each one lands |
| `discovery` | Questions grouped by theme |
| `proof_points` | Stat cards with source links |
| `talk_track` | Positioning statement, pitch, opener, trap |
| `dos_donts` | Selling hygiene |
| `pricing` | Commercial models plus ground rules |
| `next_steps` | Numbered steps and linked resources |
| `one_pager` | The dense printable card |

### Using the web builder

Open `/battlecard`, name the competitor, pick the Impact Analytics product, then press
**Load starter card**. The starter fills every section with structure and prompts. Competitor
facing fields carry research prompts rather than claims, because nothing in this repository
asserts a fact about a rival. Edit, press **Review copy** to check the brand writing rules,
then press **Build PPTX**.

Import and export JSON so a team can version a card in git.

### Using the API

```bash
# Presets: products, solutions, competitor list, section list
curl localhost:5000/api/battlecard/presets

# A prefilled card to edit
curl -X POST localhost:5000/api/battlecard/scaffold \
  -H 'Content-Type: application/json' \
  -d '{"competitor":"Example Rival","ia_product":"PriceSmart"}' > card.json

# Brand and completeness check, no file written
curl -X POST localhost:5000/api/battlecard/validate \
  -H 'Content-Type: application/json' -d @card.json

# Build the deck
curl -X POST localhost:5000/api/battlecard/build \
  -H 'Content-Type: application/json' -d @card.json
```

`build` returns the download URL, the slide count, brand warnings and the Google Slides
compatibility report.

### Using it from Python

```python
from battlecards import scaffold, normalize, validate, build_presentation, audit

card = normalize(scaffold('Example Rival', 'PriceSmart'))
print(validate(card)['warnings'])
build_presentation(card).save('battlecard.pptx')
print(audit('battlecard.pptx'))
```

## Brand compliance

The builder encodes the brand guide rather than approximating it.

**Colour.** Only the official palette reaches a slide: Impact Blue `#264CD7`, Off-White
`#F4F4F6`, Black `#1C1B1B`, White, Accent Orange `#FF6F1C`, and Gray 1 through 3. The four
use-case colours map to solutions, and a card uses exactly one of them, since the guide bans
mixing solution colours in a single composition. Picking an IA product picks the solution,
which picks the accent. Accent Orange appears in one place only, the `Gap` rating in the
matrix, which keeps it an accent. `tests/test_battlecard.py` scans the generated XML and fails
on any colour outside this set.

**Typography.** Inter Tight everywhere, set on every run and in the theme font scheme. ABC Otto
is licensed and rarely installed, so the guide specifies Inter Tight for PPTX. Spectral is
available as the serif headline option through `options.serif_headings`.

**Logo.** The bundled logo is the primary horizontal mark, Impact Blue plus Black on
transparency. On Impact Blue fills the builder generates the white variant the guide requires,
recolouring opaque pixels and preserving the shape, the spacing and full opacity. Clear space
and the 0.75in minimum width are respected.

**Pattern.** The cover carries the primary grid pattern, thin white lines at 10 percent opacity
with grain, bleeding off every edge. It ships as one cached PNG rather than hundreds of
hairline shapes.

**Voice.** `battlecards/schema.py` strips em dashes and en dashes on the way in, then flags
sentences that end with a preposition, `FAQ` used as a heading, and statistics dated before
2025. Warnings surface in the UI and in the `validate` response.

## Google Slides compatibility

Google Slides imports a subset of OOXML. The builder stays inside it:

- Exact 16:9 canvas, 12192000 by 6858000 EMU.
- Every slide is drawn on the blank layout with explicit geometry and fills. Nothing inherits
  from a master or a theme.
- Every run names its typeface on the latin, east asian and complex script slots.
- No shrink on overflow. Google Slides ignores PowerPoint's `fontScale`, so
  `battlecards/brand.py` measures wrapped text and picks a size that fits before the file is
  written.
- Tables carry explicit cell fills, borders and fonts, and the theme table style is removed so
  Slides cannot substitute its own banding.
- Preset shapes only. No custom geometry, no 3-D, no shadows, no glow, no reflections.
- Bullets use `buChar` with an explicit hanging indent rather than an inherited list style.
- Links are limited to `http` and `https`. A `javascript:` URL never reaches a slide.

`battlecards/compat.py` audits any PPTX against these rules and returns findings. The builder
runs it on every deck, and the result rides along in the build response. To open a deck: upload
the file to Google Drive, then open it with Google Slides.

## Layout

```
battlecards/
  brand.py       palette, type scale, geometry, Google Slides safe drawing primitives
  patterns.py    cached grid and dot overlays
  schema.py      data model, normalisation, validation, brand copy rules
  library.py     IA portfolio, capability and question banks, competitor presets, scaffold
  builder.py     slide builders, pagination, the deck assembler
  compat.py      Google Slides compatibility audit
  service.py     glue for the Flask routes
templates/
  battlecard.html   the builder UI
tests/
  test_battlecard.py
```
