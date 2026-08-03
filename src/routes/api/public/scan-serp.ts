/**
 * scan-serp.ts — the dedicated search source. Runs one ICP-tuned query per
 * search-derived signal through the configured search backend (SerpAPI /
 * Google CSE) to fetch grounded, current results, then classifies them.
 *
 * Classification is two-tier for accuracy:
 *   - If ANTHROPIC_API_KEY is set, Claude judges the real fetched results per
 *     signal — domain-guarded and ICP-strict, citing only the provided URLs.
 *     This is what fixes similarly-named-company misfires (fila.com → F.I.L.A.)
 *     and generic, non-ICP matches.
 *   - Otherwise it falls back to the deterministic keyword classifier.
 *
 * Accepts POST { company, domain }; the domain is threaded through both tiers.
 * Never throws.
 */

import type { CatalogId, FunctionResult, Signal } from "../../../lib/scan-contract";
import { fillQuery, NEWS_SEARCH } from "../../../lib/icp";
import { getSearchProvider, type Hit } from "./providers/search-provider";
import { classifySignal } from "./providers/classify";
import { classifyWithLLM, llmClassifyAvailable, type SignalCandidates } from "./providers/llm-classify";

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

    // 1. Fetch grounded results per signal (one query each, concurrency-capped).
    const groups: SignalCandidates[] = [];
    const CONCURRENCY = 3;
    for (let i = 0; i < SEARCH_SIGNALS.length; i += CONCURRENCY) {
      const batch = SEARCH_SIGNALS.slice(i, i + CONCURRENCY);
      const fetched = await Promise.all(
        batch.map(async (id): Promise<SignalCandidates> => {
          const cfg = NEWS_SEARCH[id]!;
          const hits: Hit[] = await provider.search(fillQuery(cfg.query, company, domain));
          return { id, hits };
        }),
      );
      groups.push(...fetched);
    }

    // 2. Classify. Prefer the accurate LLM pass over the real results; fall back
    //    to the deterministic keyword classifier when no Anthropic key.
    let signals: Signal[] | null = null;
    let classifier = "deterministic";
    if (llmClassifyAvailable()) {
      signals = await classifyWithLLM(company, domain, groups);
      if (signals) classifier = "llm-grounded";
    }
    if (!signals) {
      signals = groups.map((g) => classifySignal(g.id, g.hits, company, domain));
    }

    return { ok: true, signals, meta: { source: provider.name, classifier } };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}
