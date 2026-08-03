/**
 * scan-serp.ts — the dedicated search source. Runs one ICP-tuned query per
 * search-derived signal through the configured search backend (SerpAPI /
 * Google CSE) and classifies the grounded results deterministically. Accepts
 * POST { company, domain }; the domain is threaded through so results about a
 * similarly-named company with a different website are rejected. Never throws.
 */

import type { CatalogId, FunctionResult, Signal } from "../../../lib/scan-contract";
import { fillQuery, NEWS_SEARCH } from "../../../lib/icp";
import { getSearchProvider } from "./providers/search-provider";
import { classifySignal } from "./providers/classify";

interface ScanInput {
  company: string;
  domain: string;
}

const SEARCH_SIGNALS = Object.keys(NEWS_SEARCH) as CatalogId[];

export async function scanSerp(input: ScanInput): Promise<FunctionResult> {
  const { company, domain } = input;
  try {
    if (!company) return { ok: false, signals: [], error: "company is required" };
    const provider = getSearchProvider();
    if (!provider.available) {
      return {
        ok: false,
        signals: [],
        error: "No search provider configured (set SERPAPI_KEY or GOOGLE_CSE_KEY + GOOGLE_CSE_CX).",
      };
    }

    // One query per signal. Run with a small concurrency cap to respect quota.
    const signals: Signal[] = [];
    const CONCURRENCY = 3;
    for (let i = 0; i < SEARCH_SIGNALS.length; i += CONCURRENCY) {
      const batch = SEARCH_SIGNALS.slice(i, i + CONCURRENCY);
      const results = await Promise.all(
        batch.map(async (id) => {
          const cfg = NEWS_SEARCH[id]!;
          const hits = await provider.search(fillQuery(cfg.query, company, domain));
          return classifySignal(id, hits, company, domain);
        }),
      );
      signals.push(...results);
    }

    return { ok: true, signals, meta: { source: provider.name } };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}
