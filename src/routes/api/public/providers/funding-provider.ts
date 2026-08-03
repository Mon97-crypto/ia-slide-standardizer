/**
 * funding-provider.ts — OPTIONAL. Supplements EDGAR with private-company M&A,
 * IPO and debt-restructuring signals sourced from the search backend. Off by
 * default (it consumes search quota); enable with SCAN_FUNDING=on. Its signals
 * overlap EDGAR's (ma_activity, ipo_preparation) and are de-duplicated at merge
 * time, so it only ever adds evidence, never double-counts. Never throws.
 */

import type { CatalogId, FunctionResult, Signal } from "../../../../lib/scan-contract";
import { CATALOG } from "../../../../lib/scan-contract";
import { fillQuery, ICP_CRITERIA } from "../../../../lib/icp";
import { getSearchProvider, type Hit } from "./search-provider";
import { classifySignal } from "./classify";
import { NEWS_SEARCH } from "../../../../lib/icp";

// Funding-specific query + keyword gates, keyed by the catalog ids they feed.
const FUNDING_SEARCH: Partial<Record<CatalogId, { query: string; must: string[] }>> = {
  ma_activity: {
    query:
      '"{company}" (acquires OR "to acquire" OR merger OR "acquisition of" OR "majority stake" OR "acquired by") (retail OR brand OR banner OR chain OR grocery OR apparel)',
    must: ["acquir", "merger", "majority stake", "buyout", "takeover"],
  },
  ipo_preparation: {
    query: '"{company}" (IPO OR "initial public offering" OR "S-1" OR "files to go public" OR "public listing")',
    must: ["ipo", "initial public offering", "go public", "s-1", "public listing"],
  },
};

export function fundingEnabled(): boolean {
  return process.env.SCAN_FUNDING === "on" && getSearchProvider().available;
}

export async function scanFunding(input: { company: string; domain: string }): Promise<FunctionResult> {
  const { company, domain } = input;
  try {
    if (!fundingEnabled()) {
      return { ok: false, signals: [], error: "Funding source disabled (set SCAN_FUNDING=on with a search key)." };
    }
    const provider = getSearchProvider();
    const ids = Object.keys(FUNDING_SEARCH) as CatalogId[];
    const signals: Signal[] = [];
    for (const id of ids) {
      const cfg = FUNDING_SEARCH[id]!;
      const hits: Hit[] = await provider.search(fillQuery(cfg.query, company, domain));
      // Reuse the classifier by temporarily supplying this id's gate through
      // classifySignal, which reads NEWS_SEARCH; funding ids aren't in it, so
      // classify inline here with the funding gate.
      signals.push(classifyFunding(id, hits, company, domain, cfg.must));
    }
    return { ok: true, signals, meta: { source: `funding:${provider.name}` } };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}

function classifyFunding(
  id: CatalogId,
  hits: Hit[],
  company: string,
  domain: string,
  must: string[],
): Signal {
  // If the id happens to be in NEWS_SEARCH, defer to the shared classifier.
  if (NEWS_SEARCH[id]) return classifySignal(id, hits, company, domain);

  const criteria = ICP_CRITERIA[id];
  const slug = domain.replace(/^www\./, "").split(".")[0].toLowerCase();
  const nameToken = company.toLowerCase().split(/\s+/)[0];
  const qualifying = hits.filter((h) => {
    const text = `${h.title} ${h.snippet} ${h.url}`.toLowerCase();
    const mentions = text.includes(slug) || (nameToken.length >= 3 && text.includes(nameToken));
    return mentions && must.some((m) => text.includes(m.toLowerCase()));
  });
  if (qualifying.length === 0) {
    return { name: id, type: CATALOG[id].type, found: false, detail: "No confirmed signals found", evidence: [], iaProducts: [], soWhat: "" };
  }
  return {
    name: id,
    type: CATALOG[id].type,
    found: true,
    detail: `${criteria.title} confirmed by ${qualifying.length} dated source${qualifying.length > 1 ? "s" : ""}.`.slice(0, 100),
    evidence: qualifying.slice(0, 5).map((h) => ({ title: h.title.slice(0, 200) || h.url, url: h.url, date: h.date })),
    iaProducts: criteria.iaProducts.slice(0, 5),
    soWhat: criteria.soWhatHint.slice(0, 140),
  };
}
