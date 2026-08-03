/**
 * scan-serp.ts — the dedicated search source.
 *
 * Runs a small set of BROAD ICP-tuned queries (plus a Reddit query and a direct
 * Reddit JSON fetch for operational-pain complaints) through the search backend,
 * pools + de-dupes the real results, then classifies the whole pool:
 *   - ANTHROPIC_API_KEY present → Claude judges every search signal from the pool,
 *     domain-guarded and ICP-strict, citing only real fetched URLs (accurate).
 *   - otherwise → deterministic keyword gate per signal over the same pool.
 *
 * Quota-efficient (~6 searches/scan for 17 signals) and accurate. Never throws.
 */

import type { FunctionResult, Signal } from "../../../lib/scan-contract";
import { BROAD_QUERIES, REDDIT_QUERY, SEARCH_SIGNAL_IDS, fillQuery } from "../../../lib/icp";
import { getSearchProvider, type Hit } from "./providers/search-provider";
import { classifySignal } from "./providers/classify";
import { classifyWithLLM, llmClassifyAvailable } from "./providers/llm-classify";
import { redditOperationalPain } from "./providers/reddit-provider";

interface ScanInput {
  company: string;
  domain: string;
}

function dedupeHits(hits: Hit[], cap = 40): Hit[] {
  const seen = new Set<string>();
  const out: Hit[] = [];
  for (const h of hits) {
    if (!h.url || seen.has(h.url)) continue;
    seen.add(h.url);
    out.push(h);
    if (out.length >= cap) break;
  }
  return out;
}

export async function scanSerp(input: ScanInput): Promise<FunctionResult> {
  const { company, domain } = input;
  try {
    if (!company) return { ok: false, signals: [], error: "company is required" };
    const provider = getSearchProvider();
    if (!provider.available) {
      return { ok: false, signals: [], error: "No search provider configured (set SERPAPI_KEY or GOOGLE_CSE_KEY + GOOGLE_CSE_CX)." };
    }

    // 1. Fetch broad queries + reddit query + direct reddit, in parallel.
    const queries = [...BROAD_QUERIES, REDDIT_QUERY].map((q) => fillQuery(q, company, domain));
    const [searchArrays, reddit] = await Promise.all([
      Promise.all(queries.map((q) => provider.search(q, 8))),
      redditOperationalPain(company),
    ]);
    const pool = dedupeHits([...searchArrays.flat(), ...reddit]);

    if (pool.length === 0) {
      // No results — return all search signals as found:false.
      return {
        ok: true,
        signals: SEARCH_SIGNAL_IDS.map((id) => classifySignal(id, [], company, domain)),
        meta: { source: provider.name, classifier: "none", hits: 0 },
      };
    }

    // 2. Classify the pool.
    let signals: Signal[] | null = null;
    let classifier = "deterministic";
    if (llmClassifyAvailable()) {
      signals = await classifyWithLLM(company, domain, pool, SEARCH_SIGNAL_IDS);
      if (signals) classifier = "llm-grounded";
    }
    if (!signals) {
      signals = SEARCH_SIGNAL_IDS.map((id) => classifySignal(id, pool, company, domain));
    }

    return { ok: true, signals, meta: { source: provider.name, classifier, hits: pool.length } };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}
