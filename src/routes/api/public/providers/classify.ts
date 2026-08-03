/**
 * classify.ts — turns grounded search hits into contract Signal objects using
 * the deterministic keyword gates in icp.ts (NEWS_SEARCH). Auditable: a signal
 * fires only when a real, dated result passes its `must` gate and no `reject`
 * term, so every fired signal carries a real evidence URL and no link is invented.
 */

import type { CatalogId, Signal } from "../../../../lib/scan-contract";
import { CATALOG } from "../../../../lib/scan-contract";
import { ICP_CRITERIA, NEWS_SEARCH } from "../../../../lib/icp";
import type { Hit } from "./search-provider";

function contains(haystack: string, terms: string[]): boolean {
  const h = haystack.toLowerCase();
  return terms.some((t) => h.includes(t.toLowerCase()));
}

/** Keep hits whose title+snippet plausibly reference the target company. */
function mentionsCompany(hit: Hit, company: string, domain: string): boolean {
  const text = `${hit.title} ${hit.snippet} ${hit.url}`.toLowerCase();
  const slug = domain.replace(/^www\./, "").split(".")[0].toLowerCase();
  const nameToken = company.toLowerCase().split(/\s+/)[0];
  return text.includes(slug) || (nameToken.length >= 3 && text.includes(nameToken));
}

/**
 * Classify hits for one signal. Returns a found:true Signal with grounded
 * evidence when at least one hit qualifies, else found:false.
 */
export function classifySignal(
  id: CatalogId,
  hits: Hit[],
  company: string,
  domain: string,
): Signal {
  const cfg = NEWS_SEARCH[id];
  const criteria = ICP_CRITERIA[id];
  const base: Signal = {
    name: id,
    type: CATALOG[id].type,
    found: false,
    detail: "No confirmed signals found",
    evidence: [],
    iaProducts: [],
    soWhat: "",
  };
  if (!cfg) return base;

  const qualifying = hits.filter((hit) => {
    if (!mentionsCompany(hit, company, domain)) return false;
    const text = `${hit.title} ${hit.snippet}`;
    if (cfg.reject && contains(text, cfg.reject)) return false;
    return contains(text, cfg.must);
  });

  if (qualifying.length === 0) return base;

  return {
    ...base,
    found: true,
    detail: `${criteria.title} confirmed by ${qualifying.length} dated source${qualifying.length > 1 ? "s" : ""}.`.slice(0, 100),
    evidence: qualifying.slice(0, 5).map((h) => ({
      title: h.title.slice(0, 200) || h.url,
      url: h.url,
      date: h.date,
    })),
    iaProducts: criteria.iaProducts.slice(0, 5),
    soWhat: criteria.soWhatHint.slice(0, 140),
  };
}
