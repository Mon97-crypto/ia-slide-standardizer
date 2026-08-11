/**
 * scan-news.ts — orchestrates the "News and hiring" tier. The heavy news-signal
 * gathering can run from either of two backends; jobs + funding always supplement
 * (neither uses SerpAPI):
 *   - Anthropic web search (scanNewsAnthropic): Claude searches AND judges in one
 *     grounded call. Zero SerpAPI credits per scan.
 *   - SerpAPI (scanSerp): ~9 searches/scan, then Claude classifies the pool.
 *
 * Which is PRIMARY is controlled by NEWS_SOURCE:
 *   - "anthropic" → always Claude web search (SerpAPI never touched for news).
 *   - "serp"      → always SerpAPI (legacy behaviour).
 *   - "auto" (default) → prefer Claude web search whenever ANTHROPIC_API_KEY is
 *     set (saves SerpAPI credits), otherwise SerpAPI.
 * The non-primary backend is used only as a FALLBACK when the primary errors, so
 * a rate-limit / quota / API blip still yields results without spending both.
 * Never throws.
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
    const hasAnthropic = anthropicAvailable();
    const mode = (process.env.NEWS_SOURCE || "auto").toLowerCase();

    // Decide the primary news backend. Default (auto): prefer Anthropic web search
    // when available to keep SerpAPI credits for when they're actually needed.
    const preferAnthropic = mode === "anthropic" ? true : mode === "serp" ? false : hasAnthropic;

    if (!hasSearch && !hasAnthropic) {
      return {
        ok: false,
        signals: [],
        error:
          "No news source configured. Set ANTHROPIC_API_KEY (Claude web search) and/or SERPAPI_KEY (or GOOGLE_CSE_KEY + GOOGLE_CSE_CX).",
      };
    }

    // Run the primary; fall back to the other backend only if the primary errored.
    const runAnthropic = () => scanNewsAnthropic(input);
    const runSerp = () => scanSerp(input);

    let primary: FunctionResult;
    if (preferAnthropic && hasAnthropic) {
      primary = await runAnthropic();
      if (!primary.ok && hasSearch) primary = await runSerp();
    } else if (hasSearch) {
      primary = await runSerp();
      if (!primary.ok && hasAnthropic) primary = await runAnthropic();
    } else {
      // preferAnthropic requested but no anthropic → fall to whatever's available.
      primary = hasAnthropic ? await runAnthropic() : await runSerp();
    }

    // Supplement with jobs + funding (independent of SerpAPI).
    const suppTasks: Array<Promise<FunctionResult>> = [scanJobs(company, domain).then(toResult)];
    if (fundingEnabled()) suppTasks.push(scanFunding(input));
    const settled = await Promise.allSettled(suppTasks);

    const signals: Signal[] = [...(primary.signals ?? [])];
    const sources: string[] = [];
    const failed: string[] = [];
    let classifier = primary.meta?.classifier ? String(primary.meta.classifier) : undefined;
    let resolvedName = primary.meta?.resolvedName ? String(primary.meta.resolvedName) : undefined;
    if (primary.meta?.source) sources.push(String(primary.meta.source));
    if (!primary.ok && primary.error) failed.push(primary.error);

    for (const s of settled) {
      if (s.status !== "fulfilled") { failed.push("provider error"); continue; }
      const r = s.value;
      if (r.ok) {
        signals.push(...r.signals);
        if (r.meta?.source) sources.push(String(r.meta.source));
        if (!classifier && r.meta?.classifier) classifier = String(r.meta.classifier);
        if (!resolvedName && r.meta?.resolvedName) resolvedName = String(r.meta.resolvedName);
      } else if (r.error) {
        failed.push(r.error);
      }
    }

    return {
      ok: primary.ok || signals.length > 0,
      signals,
      meta: { sources, failed, classifier, resolvedName },
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
