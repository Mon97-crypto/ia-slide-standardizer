/**
 * reddit-provider.ts — operational-pain signals from Reddit. Retail out-of-stock,
 * quality and inventory complaints surface on Reddit before the trade press.
 * Uses Reddit's public search JSON (no key; a descriptive User-Agent is required
 * and it's rate-limited). Returns grounded hits merged into the operational_pain
 * candidate pool. Never throws.
 */

import type { Hit } from "./search-provider";

const UA = process.env.REDDIT_USER_AGENT || "ImpactAnalytics-AccountScanner/1.0 (research)";

export async function redditOperationalPain(company: string): Promise<Hit[]> {
  const q = `${company} (inventory OR "out of stock" OR stockout OR markdown OR "poor quality" OR complaint)`;
  const url = `https://www.reddit.com/search.json?q=${encodeURIComponent(q)}&sort=relevance&t=year&limit=15`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(url, { headers: { "User-Agent": UA, Accept: "application/json" }, signal: controller.signal });
    if (!res.ok) return [];
    const data = (await res.json()) as {
      data?: { children?: Array<{ data?: Record<string, unknown> }> };
    };
    const children = data.data?.children ?? [];
    return children
      .map((c) => c.data ?? {})
      .map((p) => ({
        title: String(p.title ?? ""),
        url: p.permalink ? `https://www.reddit.com${p.permalink}` : String(p.url ?? ""),
        date: p.created_utc ? new Date(Number(p.created_utc) * 1000).toISOString().slice(0, 10) : "",
        snippet: String(p.selftext ?? "").slice(0, 240) || `r/${String(p.subreddit ?? "")} discussion`,
      }))
      .filter((h) => h.url);
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}
