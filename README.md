# IA Battlecard Builder

A competitive battlecard builder for Impact Analytics. Pick a competitor, pick an IA
product, pick a length, and Claude researches the public record and writes the deck.

- **Battlecard Builder** at `/` is the product. Three inputs, a chat assistant, and a
  PPTX download.
- **Slide Standardizer** at `/standardizer` is the original tool, kept but no longer the
  front door.

Every deck follows the Impact Analytics brand guide and opens unchanged in PowerPoint,
Keynote and Google Slides.

## How generation works

1. **Research.** Claude Opus 5 searches the public record with the `web_search` server
   tool and writes a sourced brief. The brief streams to the browser while it is written,
   so a run that takes minutes never looks stalled and never trips a worker timeout.
2. **Structure.** A second call turns the brief into the card schema through structured
   outputs, so the payload validates without parsing prose.
3. **Merge.** Where a hand researched card exists in `content/battlecards/`, its sourced
   sections win. The model fills gaps rather than overwriting research.
4. **Build.** The card is normalised, trimmed to the chosen depth, checked against the
   brand writing rules, and rendered to PPTX.

**The honesty design is the point.** Claude receives the IA product facts as ground truth
and is instructed never to state a competitor capability, number, customer or price it did
not source. Where the public record is silent, the capability rating comes back `unknown`,
which the deck renders as "Unclear" with "Ask the question, do not assert the gap". A
battlecard that overstates a rival's gap loses the deal the moment the buyer corrects it,
so the builder would rather hand a seller a question than a guess.

### Depths

| Depth | Slides | What it is |
|---|---|---|
| Summary | 6 to 8 | The one page card plus the essentials |
| Standard | 11 to 13 | The working card for most meetings |
| Full technical | 17 to 20 | Every section, including the capability matrix and pricing |

Depth caps rows per section, so a summary stays a summary. A card that names its own
sections, such as the curated files in `content/`, is never trimmed.

## Running it

```bash
pip install -r requirements.txt
python3 app.py                                  # http://127.0.0.1:5000
python3 build_battlecards.py                    # build every card in content/
python3 -m pytest tests -q
```

### Environment

| Variable | Effect when unset |
|---|---|
| `ANTHROPIC_API_KEY` | No research and no assistant. Saved cards still build. |
| `IA_AUTH_USER`, `IA_AUTH_PASSWORD` | Every route is open. Unsafe with real content. |

### Access control

Set `IA_AUTH_USER` and `IA_AUTH_PASSWORD` to gate every route behind HTTP basic
auth. Battlecards hold competitive intelligence and unpublished customer numbers,
so a deployment with real content needs both. `/healthz` and `/static/` stay open
so the platform probe keeps working. With the variables unset the app runs open
and logs a warning. No credential lives in this repository.

Docker and Render configuration already exist in `Dockerfile` and `render.yaml`.

## Battlecard Builder

### What it produces

A battlecard deck of up to 16 sections. Long sections paginate on their own, so seven
objections become four slides without any manual work.

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
| `proof_points` | Stat cards with a source link or an internal citation |
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
# Is Claude reachable, and what depths exist
curl localhost:5000/api/battlecard/status

# Research a competitor and stream the card back as server sent events
curl -N -X POST localhost:5000/api/battlecard/generate \
  -H 'Content-Type: application/json' \
  -d '{"competitor":"o9 Solutions","ia_product":"AttributeSmart","depth":"summary"}'

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

### AttributeSmart cards

`battlecards/attributesmart.py` holds a deep card set for AttributeSmart against
Oracle Retail, Blue Yonder, RELEX Solutions and o9 Solutions. The four rendered
payloads live in `content/battlecards/`, so they version in git and rebuild on
demand with `build_battlecards.py`.

Two rules govern that module. The Impact Analytics side is specific, drawn from
the AttributeSmart NRF 2026 deck and cited to it. The competitor side states only
what public material supports, with a source on every card; where the record is
silent the capability rating is `Unclear` and the seller is told to ask rather
than handed a guess. `test_unsourced_competitor_capabilities_stay_unknown` enforces
that. A card that overstates a rival's gap loses the deal the moment the buyer
corrects it.

**Category note.** AttributeSmart *generates* attributes from images, labels and
text. Those four vendors mostly *consume* attributes for planning, and Oracle is
the only one shipping a directly competing extraction product. The vendors that
actually compete on generation are listed in `DIRECT_RIVALS`: Lily AI, Vue.ai,
Pixyle AI, Syndigo, Salsify and Akeneo.

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

**Typography.** Inter Tight everywhere, set on every run and in the theme font scheme, with
Lato for the footer. Both were confirmed against the house deck, which uses 1357 Inter Tight
runs and 813 Lato runs. ABC Otto is licensed and rarely installed, so the guide specifies
Inter Tight for PPTX. Spectral is available as the serif headline option through
`options.serif_headings`.

**House template devices**, measured from the IA AttributeSmart deck and reproduced here: the
10 by 5.625in canvas, two tone titles that split a Black phrase from an Impact Blue emphasis,
whitespace rather than a rule under the title, white rounded cards with a soft shadow and no
edge stripe, blue pill headers, and stat cards with an inner tinted panel under an italic
label. The Data and Intelligence accent follows the shipping theme at `#BFD1F5`, which
disagrees with `visual-specs.md`; the theme wins.

**Logo.** The bundled logo is the primary horizontal mark, Impact Blue plus Black on
transparency. On Impact Blue fills the builder generates the white variant the guide requires,
recolouring opaque pixels and preserving the shape, the spacing and full opacity. Clear space
and the 0.75in minimum width are respected.

**Pattern.** The cover carries the primary grid pattern, thin white lines at 10 percent opacity
with grain, bleeding off every edge. It ships as one cached PNG rather than hundreds of
hairline shapes.

**Voice.** `battlecards/schema.py` strips em dashes and en dashes on the way in, then flags
sentences that end with a preposition, `FAQ` used as a heading, and statistics dated before
2025. Warnings surface in the UI and in the `validate` response. A proof point may cite an
internal source that names its year, such as a deck title; a card marked
`meta.distribution: customer` still demands a public link.

## Google Slides compatibility

Google Slides imports a subset of OOXML. The builder stays inside it:

- Exact 16:9 canvas, 9144000 by 5143500 EMU, which is the 10 by 5.625in size the IA
  template uses, so a slide pastes into a house deck without rescaling.
- Every slide is drawn on the blank layout with explicit geometry and fills. Nothing inherits
  from a master or a theme.
- Every run names its typeface on the latin, east asian and complex script slots.
- No shrink on overflow. Google Slides ignores PowerPoint's `fontScale`, so
  `battlecards/brand.py` measures wrapped text and picks a size that fits before the file is
  written.
- Tables carry explicit cell fills, borders and fonts, and the theme table style is removed so
  Slides cannot substitute its own banding.
- Preset shapes only. No custom geometry, no 3-D, no glow, no reflections. An outer shadow
  is the one effect used, because Google Slides both imports it and exposes it in its own
  editor.
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
  ai.py          Claude Opus 5 research, structured card generation, chat assistant
  attributesmart.py  deep AttributeSmart card set, IA facts plus sourced rivals
  auth.py        optional HTTP basic auth over every route
  service.py     glue for the Flask routes
content/battlecards/
  *.json            versioned battlecard payloads
build_battlecards.py  build every card from content/
templates/
  battlecard.html   the builder UI, the landing page
  index.html        the original standardizer, at /standardizer
tests/
  test_battlecard.py
```
