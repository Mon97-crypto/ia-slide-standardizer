/**
 * scan-news.ts — orchestrates the dedicated per-source providers into the
 * "News and hiring" tier the frontend expects. It composes:
 *   - scan-serp   (search API): 9 news-derived signals
 *   - jobs feed:   hiring_activity, no_job_openings
 *   - funding:     optional ma_activity / ipo_preparation supplements
 *
 * If no search key is configured but ANTHROPIC_API_KEY is, it falls back to the
 * single Anthropic web-search classifier so the tier still works. If nothing is
 * configured it returns ok:false naming the keys to set. Never throws.
 */

import type { FunctionResult, Signal } from "../../../lib/scan-contract";
import { scanSerp } from "./scan-serp";
import { scanJobs } from "./providers/jobs-provider";
import { scanFunding, fundingEnabled } from "./providers/funding-provider";
import { getSearchProvider } from "./providers/search-provider";
import { anthropicAvailable, scanNewsAnthropic } from "./providers/anthropic-provider";

interface ScanInput {
  company: string;
  domain: string;
}

export async function scanNews(input: ScanInput): Promise<FunctionResult> {
  const { company, domain } = input;
  try {
    if (!company) return { ok: false, signals: [], error: "company is required" };

    const hasSearch = getSearchProvider().available;

    // Fallback: no dedicated search key, but Anthropic is available.
    if (!hasSearch) {
      if (anthropicAvailable()) return scanNewsAnthropic(input);
      return {
        ok: false,
        signals: [],
        error:
          "No news source configured. Set SERPAPI_KEY (or GOOGLE_CSE_KEY + GOOGLE_CSE_CX) for search, and a jobs key for hiring. ANTHROPIC_API_KEY also works as a single-source fallback.",
      };
    }

    const tasks: Array<Promise<FunctionResult>> = [scanSerp(input), scanJobs(company, domain).then(toResult)];
    if (fundingEnabled()) tasks.push(scanFunding(input));

    const settled = await Promise.allSettled(tasks);
    const signals: Signal[] = [];
    const sources: string[] = [];
    const failed: string[] = [];

    for (const s of settled) {
      if (s.status !== "fulfilled") {
        failed.push("provider error");
        continue;
      }
      const r = s.value;
      if (r.ok) {
        signals.push(...r.signals);
        if (r.meta?.source) sources.push(String(r.meta.source));
      } else if (r.error) {
        failed.push(r.error);
      }
    }

    // ok as long as at least one provider produced signals.
    return {
      ok: signals.length > 0 || sources.length > 0,
      signals,
      meta: { sources, failed },
    };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}

/** Adapt the jobs provider's return to the uniform FunctionResult envelope. */
function toResult(j: { available: boolean; signals: Signal[]; error?: string }): FunctionResult {
  return {
    ok: j.available,
    signals: j.signals,
    meta: j.available ? { source: "jobs" } : undefined,
    error: j.error,
  };
}
