# Competitor Intelligence · Impact Analytics

A shared, searchable library of competitor material with grounded AI analysis.
Upload a battlecard, client list or research note, then search the whole library
the way an analyst actually types: `o9 battlecard`, `jda pricing`, `relex clients`.

Runs as a single container. No separate frontend build, no external database.

## What it does

**Search that understands the query.** A query is parsed into a competitor, a
document type and residual text before anything is matched. `o9 battlecard`
resolves to competitor `o9 Solutions` plus category `battlecard`. `jda` resolves
to Blue Yonder, because that is the same company under its former name.
Misspellings such as `bleu yonder` still land on the right company. Every result
shows why it matched.

**Full text across real document formats.** PDF, DOCX, PPTX, XLSX, CSV, TXT and
Markdown are parsed on upload, indexed with SQLite FTS5, and split into
overlapping passages. Searching `legacy architecture` finds the sentence inside
a PDF, not just a title.

**Grounded answers with citations.** Analyze extracts a structured competitor
profile. Ask answers questions from passages retrieved out of the library rather
than from a truncated prefix of one file, and cites the entries it used.

**Battlecards built from the whole library.** The generator sweeps the library
once per theme, covering positioning, pricing, implementation, customers,
product gaps and technology posture, then attributes each passage to the theme
that scores it best. The result is a structured card with plays, discovery
questions, objection handling, landmines, proof points and an explicit list of
what the library does not yet cover, alongside a confidence rating so a thin
card announces itself rather than reading like a thorough one.

**One shared library that persists.** Everything lives in a server-side
database, so the whole team sees the same data. Point `DATABASE_URL` at a
managed Postgres and the library survives deploys and restarts; without it the
app falls back to local SQLite, which is fine for development.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set ANTHROPIC_API_KEY
python app.py                 # http://localhost:5000
```

Run the tests with `python -m pytest tests/ -q`.

## Deploying on Render

### 1. Create a free Postgres

Render's filesystem is ephemeral. Without an external database the library is
wiped on every deploy, so create the database first.

Any managed Postgres works. Free options that do not expire:

- **Neon** at neon.tech, create a project, copy the connection string.
- **Supabase** at supabase.com, Project Settings, Database, copy the URI.

Render's own Postgres also works, but its free tier expires after 30 days.

Copy the connection string. It looks like
`postgresql://user:password@host/dbname`. Neon and Supabase require TLS, so
append `?sslmode=require` if the string does not already carry it.

### 2. Create the web service

Point Render at this repo. The `render.yaml` blueprint builds the Dockerfile on
the free plan. Set these in the dashboard, not in git:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | The Postgres connection string from step 1. This is what makes the library permanent. |
| `ANTHROPIC_API_KEY` | Enables Analyze, Ask and battlecards. Everything else works without it. |
| `CIQ_ADMIN_PASSCODE` | Admin passcode. Change it from the default. |
| `CIQ_SECRET_KEY` | Signs admin sessions. `render.yaml` generates one. |

The schema is created automatically on first boot, so there is no migration
step. `/healthz` reports which backend is live:

```json
{"ok": true, "backend": "postgres", "ai_enabled": true, "entries": 0}
```

If `backend` says `sqlite`, `DATABASE_URL` did not reach the service and your
data will not survive the next deploy.

## Configuration

See `.env.example`. Notable settings:

- `CIQ_MODEL` selects the Claude model, default `claude-opus-5`.
- `CIQ_ALLOW_REMOTE_FETCH` toggles fetching of shared cloud links.
- `CIQ_MAX_UPLOAD_BYTES` caps upload size, default 25 MB.

## How the AI is wired

The Anthropic key is read on the server and never reaches the browser. Requests
go out through the official `anthropic` SDK, so a page viewer cannot read the
key from source. With no key configured the API returns a clear 503 explaining
that AI is off, and the header shows an "AI off" badge, rather than failing
silently.

Shared cloud links are fetched by the server, restricted to an allowlist of
document hosts, and rejected when a link resolves to a private address. Nothing
is relayed through third party CORS proxies.

## Layout

```
app.py             Flask routes and API
ciq/config.py      environment configuration
ciq/competitors.py competitor aliases and IA product mapping
ciq/db.py          SQLite store and FTS5 indexes
ciq/ingest.py      document text extraction and chunking
ciq/fetchers.py    server side cloud link fetching
ciq/search.py      query parsing, ranking and passage retrieval
ciq/llm.py         Claude integration
templates/         the single page UI
tests/             pytest suite
legacy/            the original IA Slide Standardizer, unchanged
```

## Importing an existing library

The Admin panel imports the JSON exported by the earlier prototype, including
base64 `fileData`, and indexes the decoded text so it becomes searchable.
