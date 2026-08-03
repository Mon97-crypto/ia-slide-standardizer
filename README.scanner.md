# IA Account Scanner

An internal Sales/BD tool for Impact Analytics. Scan any retailer for buying
signals — SEC filings, tech stack, and news/hiring — weighted for how well the
account fits what Impact Analytics sells.

> Note: this repository is named `ia-slide-standardizer` and still contains the
> original Python Flask slide tool (`app.py`, `templates/`, `Dockerfile.slides`).
> The scanner was added alongside it. Nothing from the slide tool was deleted.

## Architecture

One deployable Node service:

```
Browser (React SPA, src/)
   │  fetch /api/public/*  (in parallel, Promise.allSettled)
   ▼
Hono API (server/index.ts) ──► src/routes/api/public/
   ├─ scan-edgar.ts      SEC EDGAR (free, no key)
   ├─ scan-techstack.ts  homepage fetch + verification (no key)
   ├─ scan-news.ts       Anthropic web-search research (ANTHROPIC_API_KEY)
   └─ apollo-contacts.ts retail-planning CXOs (APOLLO_API_KEY)
   └─ 24h scans cache (server/cache.ts, JSON file — swappable for a DB)
```

- **Secrets are server-side only.** API-route files live under `src/routes/` but
  are imported *only* by `server/index.ts`, so keys never reach the browser bundle.
- **Scoring is frontend-only** (`src/lib/scan-contract.ts`). Edge functions return
  raw signal objects; the client looks up weights/types from the catalog.
- **ICP relevance** lives in `src/lib/icp.ts` — the file to tune over time.

## Signal model

16 canonical catalog ids (`scan-contract.ts`), scored to an intent level:
Disqualified · Poor fit · Neutral · Potential buyer · Strong buyer.

`icp.ts` layers Impact-Analytics-specific qualifying criteria, competitor
vocabulary, search query groups, and per-signal `iaProducts` + `soWhat` onto
those ids without renaming them.

## Develop

```bash
npm install
npm run dev        # Vite on :5173 proxies /api to Hono on :8787
```

## Build & run (production)

```bash
npm run build      # typecheck + vite build → dist/
npm start          # Hono serves dist/ and /api on $PORT (default 8787)
```

## Deploy

`Dockerfile` + `render.yaml` deploy the scanner as a single Docker web service.
Set `ANTHROPIC_API_KEY` and `APOLLO_API_KEY` in the host dashboard (never commit
them). The SEC and tech-stack tiers need no keys.

## Environment notes

External calls (SEC, Anthropic, Apollo) require an environment with outbound
network access. Every function is written to *never throw* and to return a
graceful fallback when a source is unreachable, so a partial scan still renders.
