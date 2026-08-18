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
   ├─ scan-news.ts       orchestrates dedicated per-source providers:
   │     providers/search-provider.ts  SerpAPI / Google CSE  → 9 news signals
   │     providers/jobs-provider.ts    SerpAPI Jobs / Adzuna → hiring signals
   │     providers/funding-provider.ts optional M&A / IPO (SCAN_FUNDING=on)
   │     providers/classify.ts         deterministic keyword gate (auditable)
   │     providers/anthropic-provider.ts  single-source fallback (optional)
   ├─ scan-serp.ts / scan-jobs / scan-funding  (also exposed individually)
   └─ apollo-contacts.ts retail-planning CXOs (APOLLO_API_KEY)
   └─ 24h scans cache (server/cache.ts, JSON file — swappable for a DB)
```

Each news signal fires only when a **real, dated** search/job result passes its
`must` keyword gate (and no `reject` term) and mentions the target company —
so every fired signal carries a grounded evidence URL and no link is invented.
The gates live in `src/lib/icp.ts` (`NEWS_SEARCH`), the file to tune over time.
Overlapping ids (e.g. EDGAR + funding both cover `ma_activity`) are de-duplicated
at merge time, so extra sources add evidence and never double-count.

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
Set the source keys in the host dashboard (never commit them); see `.env.example`
for the full list. The SEC and tech-stack tiers need no keys.

| Key | Enables |
|-----|---------|
| `SERPAPI_KEY` *(or `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX`)* | 9 news signals via search |
| `SERPAPI_KEY` *(or `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`)* | hiring signals via jobs feed |
| `SCAN_FUNDING=on` *(needs a search key)* | optional private-company M&A / IPO |
| `APOLLO_API_KEY` | retail-planning CXO contacts |
| `ANTHROPIC_API_KEY` | optional single-source fallback for the news tier |

Every tier degrades gracefully: a missing key returns a clear "set X" message and
the scan still renders with the sources that are configured.

## Environment notes

External calls (SEC, Anthropic, Apollo) require an environment with outbound
network access. Every function is written to *never throw* and to return a
graceful fallback when a source is unreachable, so a partial scan still renders.
