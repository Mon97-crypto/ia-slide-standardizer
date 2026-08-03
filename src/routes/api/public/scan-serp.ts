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
import { resolveEntity } from "./account-info";

interface ScanInput {
  company: string;
  domain: string;
}

function dedupeHits(hits: Hit[], cap = 60): Hit[] {
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

/**
 * Drop hits whose date is clearly older than ~13 months. Undated hits are kept
 * (SerpAPI often omits the date); the query-level recency filter + the classifier
 * handle those. Reddit permalinks (no parseable date) are always kept.
 */
function dropStale(hits: Hit[]): Hit[] {
  const cutoff = Date.now() - 400 * 24 * 60 * 60 * 1000; // ~13 months of slack
  return hits.filter((h) => {
    if (!h.date) return true;
    const t = Date.parse(h.date);
    if (Number.isNaN(t)) return true; // relative/opaque date — keep, let the LLM judge
    return t >= cutoff;
  });
}

export async function scanSerp(input: ScanInput): Promise<FunctionResult> {
  const { company, domain } = input;
  try {
    if (!company) return { ok: false, signals: [], error: "company is required" };
    const provider = getSearchProvider();
    if (!provider.available) {
      return { ok: false, signals: [], error: "No search provider configured (set SERPAPI_KEY or GOOGLE_CSE_KEY + GOOGLE_CSE_CX)." };
    }

    // 0. Resolve the EXACT company for this domain (official name + industry) so
    // searches use "Gap Inc." not the word "gap", and the sportswear brand at
    // fila.com not F.I.L.A. Group. Falls back to the caller's guess.
    const entity = await resolveEntity(company, domain);
    const name = entity.name;

    // 1. Fetch broad queries (recent-only) + reddit, in parallel. The Reddit brand
    // query and direct fetch use the informal brand name (the caller's guess).
    const queries = BROAD_QUERIES.map((q) => fillQuery(q, name, domain));
    const redditQ = fillQuery(REDDIT_QUERY, company, domain);
    const [searchArrays, redditSearch, reddit] = await Promise.all([
      Promise.all(queries.map((q) => provider.search(q, 10, true))),
      provider.search(redditQ, 10, true),
      redditOperationalPain(company),
    ]);
    const pool = dropStale(dedupeHits([...searchArrays.flat(), ...redditSearch, ...reddit]));

    if (pool.length === 0) {
      // No results — return all search signals as found:false.
      return {
        ok: true,
        signals: SEARCH_SIGNAL_IDS.map((id) => classifySignal(id, [], name, domain)),
        meta: { source: provider.name, classifier: "none", hits: 0, resolvedName: name },
      };
    }

    // 2. Classify the pool, keyed to the resolved entity + industry.
    let signals: Signal[] | null = null;
    let classifier = "deterministic";
    if (llmClassifyAvailable()) {
      signals = await classifyWithLLM(name, domain, pool, SEARCH_SIGNAL_IDS, { industry: entity.industry });
      if (signals) classifier = "llm-grounded";
    }
    if (!signals) {
      signals = SEARCH_SIGNAL_IDS.map((id) => classifySignal(id, pool, name, domain));
    }

    return { ok: true, signals, meta: { source: provider.name, classifier, hits: pool.length, resolvedName: name } };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}
