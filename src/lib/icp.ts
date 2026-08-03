/**
 * icp.ts — Impact Analytics ideal-customer-profile vocabulary.
 *
 * The single place that decides whether a signal is "something Impact Analytics
 * can sell into." Tune this file over time. Endpoints and the classifier import
 * from here rather than duplicating strings.
 */

import type { CatalogId } from "./scan-contract";

// ── PRODUCT PORTFOLIO — five pillars ────────────────────────────────────────────
export const IA_PRODUCTS = {
  merchandising: ["PlanSmart", "ItemSmart", "AssortSmart", "SizeSmart", "StoreSmart", "VisualSmart"],
  inventoryReplenishment: ["ForecastSmart", "InventorySmart", "SpaceSmart"],
  pricingPromotions: ["PriceSmart", "MarkSmart", "BaseSmart", "PromoSmart", "TradeSmart"],
  dataIntelligence: ["MondaySmart", "TestSmart", "AttributeSmart", "DataSmart"],
  agenticServices: [
    "Platform Agents", "Agentic Retail Automation", "CortexEye",
    "Data Engineering", "Retail Analytics", "Pricing War Room", "Sizing as a Service",
  ],
} as const;

export const ALL_PRODUCT_NAMES: string[] = Object.values(IA_PRODUCTS).flat();
const PRODUCT_LOOKUP = new Map(ALL_PRODUCT_NAMES.map((p) => [p.toLowerCase(), p]));

export function sanitizeProducts(products: unknown): string[] {
  if (!Array.isArray(products)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of products) {
    if (typeof raw !== "string") continue;
    const match = PRODUCT_LOOKUP.get(raw.trim().toLowerCase());
    if (match && !seen.has(match)) {
      seen.add(match);
      out.push(match);
    }
  }
  return out.slice(0, 5);
}

// ── TARGET INDUSTRIES ───────────────────────────────────────────────────────────
export const TARGET_INDUSTRIES = [
  "retail — apparel, footwear and accessories", "retail — grocery", "retail — specialty",
  "retail — department store", "retail — furniture", "retail — electronics and appliances",
  "retail — home improvement", "CPG and OTC manufacturing", "wholesale and distribution",
  "quick-service restaurants",
] as const;

// ── COMPETITORS — incumbent presence is our strongest buying signal ──────────────
export const COMPETITORS = [
  "RELEX", "o9 Solutions", "Blue Yonder", "JDA", "Oracle Retail", "SAP", "Aptos", "Anaplan",
  "Invent Analytics", "First Insight", "Revionics", "Zilliant", "PROS", "ToolsGroup", "Logility",
  "Kinaxis", "Manhattan Associates", "Symphony RetailAI", "Antuit.ai", "Increff", "7thonline",
  "NielsenIQ", "Circana", "SAS",
] as const;

export const LEGACY_PLANNING_TERMS = [
  "Excel-based planning", "spreadsheet planning", "manual planning", "manual forecasting", "manual allocation",
];

// ── PER-SIGNAL QUALIFYING CRITERIA (all 19) ─────────────────────────────────────
export interface IcpCriteria {
  title: string;
  qualify: string;
  reject?: string;
  iaProducts: string[];
  soWhatHint: string;
}

export const ICP_CRITERIA: Record<CatalogId, IcpCriteria> = {
  // KEY
  tech_stack_change: {
    title: "Current tech stack",
    qualify: "The company's current web/cloud/data stack — modern frameworks (React, Angular, Vue), cloud (AWS), and any named data-platform or retail-planning tooling detected.",
    iaProducts: ["Platform Agents", "DataSmart"],
    soWhatHint: "Their plumbing shapes integration effort. Modern stack = faster IA deployment.",
  },
  rfp_rfq_rfi: {
    title: "RFP, RFQ or RFI",
    qualify: "A public RFP/RFQ/RFI for retail planning, merchandising, forecasting, assortment, pricing, promotion, markdown, inventory/allocation, space planning, attribution, retail BI or a data platform.",
    reject: "Construction, facilities, legal panels, staffing, media buying, carriers/logistics.",
    iaProducts: ["PlanSmart", "AssortSmart", "ForecastSmart", "PriceSmart", "InventorySmart"],
    soWhatHint: "An active buying process is open. Respond directly to the stated scope.",
  },
  ma_activity: {
    title: "M&A activity",
    qualify: "A merger, acquisition or majority investment. Note whether it adds banners or categories — multi-banner complexity forces assortment rationalization and planning-system consolidation.",
    reject: "Rumor or analyst speculation with no confirmed transaction.",
    iaProducts: ["PlanSmart", "AssortSmart", "ItemSmart"],
    soWhatHint: "Integration forces banner/category consolidation. Lead with one planning hierarchy across banners.",
  },
  geographic_expansion: {
    title: "Geographic expansion",
    qualify: "Entry into a new country, region or market. New demand curves, localized assortments, different size curves.",
    reject: "A single pop-up or temporary seasonal location.",
    iaProducts: ["ForecastSmart", "AssortSmart", "SizeSmart"],
    soWhatHint: "New geography = demand curves the current model has never seen. Lead with localized forecasting.",
  },
  operational_pain: {
    title: "Operational pain",
    qualify: "A confirmed inventory or price problem: stockouts, low on-shelf availability, overstock, excess/aged inventory, write-downs, heavy/unplanned markdowns, margin erosion, forecast-accuracy misses, allocation errors, size/fit problems, high returns, poor sell-through, shrink, or supply-chain delays showing as misplaced inventory. Reddit complaints about out-of-stocks count.",
    reject: "Data breaches, employment lawsuits, food-safety recalls, ESG criticism, and service complaints unrelated to inventory or price.",
    iaProducts: ["ForecastSmart", "InventorySmart", "MarkSmart", "SizeSmart", "PriceSmart"],
    soWhatHint: "Highest-value signal. Lead with the named pain and the product that fixes it, quantified.",
  },
  leadership_change: {
    title: "Leadership changes",
    qualify: "Any ICP-adjacent leadership move — a hire, an exit, or an internal promotion: Chief Merchandising Officer/Chief Merchant, GMM/DMM, Chief Supply Chain Officer, COO, CIO, CTO, Chief Digital Officer, Chief Data/Analytics Officer, CFO, Chief Stores Officer, or VP of Planning, Allocation, Merchandising, Pricing, Demand Planning, Inventory or Retail Technology.",
    reject: "CHRO, Chief People Officer, General Counsel, brand/advertising CMO, Chief Communications Officer, Chief Sustainability Officer, and articles about FORMER employees or alumni.",
    iaProducts: ["PlanSmart", "AssortSmart", "ForecastSmart", "PriceSmart"],
    soWhatHint: "New leaders re-evaluate the stack early. Lead with a quick win in their function.",
  },
  erp_crm_migration: {
    title: "ERP, CRM or cloud migration",
    qualify: "An active migration with a change verb (implementing, migrating, deploying, replacing, rolling out). Highest value: SAP S/4HANA, Oracle Retail/Fusion, Blue Yonder, Manhattan, NetSuite, Microsoft Dynamics, and data-platform moves to Snowflake, Databricks or BigQuery.",
    reject: "Generic 'digital transformation' releases and vendor pages naming no system, or a partnership/integration announcement.",
    iaProducts: ["DataSmart", "ForecastSmart", "InventorySmart", "PlanSmart", "Platform Agents"],
    soWhatHint: "A modern data platform going live is exactly who can deploy IA next. Lead with time-to-value.",
  },
  bankruptcy: {
    title: "Bankruptcy",
    qualify: "Chapter 11, administration or insolvency filing. Likely disqualifies near-term purchase; note that emergence from restructuring is a replatforming window.",
    iaProducts: ["InventorySmart", "MarkSmart"],
    soWhatHint: "Near-term risk; watch for emergence — restructuring exits replatform.",
  },
  store_expansion: {
    title: "Stores / facility expansion",
    qualify: "New stores, distribution centres or fulfilment centres. More nodes make allocation harder.",
    iaProducts: ["InventorySmart", "StoreSmart", "SpaceSmart"],
    soWhatHint: "More nodes scramble allocation. Lead with allocation and space planning across the larger fleet.",
  },
  vendor_sentiment: {
    title: "Current vendor sentiment",
    qualify: "Praise, frustration, non-renewal, failed implementation or analyst criticism of an incumbent planning/pricing vendor (RELEX, o9, Blue Yonder, Oracle, SAP, Aptos, Logility, Manhattan, etc.). Dissatisfaction is our strongest displacement signal.",
    reject: "Mentions of vendors unrelated to planning/pricing/inventory.",
    iaProducts: ["PlanSmart", "ForecastSmart", "PriceSmart", "InventorySmart"],
    soWhatHint: "Dissatisfaction with an incumbent is the strongest displacement opening. Time a play at renewal.",
  },
  // SUPPORTING
  new_product_line: {
    title: "New product line",
    qualify: "A new category, brand or private label.",
    iaProducts: ["AssortSmart", "AttributeSmart", "SizeSmart"],
    soWhatHint: "New categories need assortment and attribution. Lead with AssortSmart/AttributeSmart.",
  },
  hiring_activity: {
    title: "Relevant hiring",
    qualify: "Open roles in planning, allocation, replenishment, inventory, pricing, markdown, promotions, category management, space/assortment planning, buying and planning, retail data science, or analytics/data engineering in a merchandising or supply-chain context. A cluster is stronger than one role. Capture any competitor tool named in a JD.",
    reject: "Store associates, cashiers, warehouse pickers, drivers, security, marketing, HR.",
    iaProducts: ["PlanSmart", "InventorySmart", "ForecastSmart", "Retail Analytics"],
    soWhatHint: "Building a planning team by hand. Lead with automation that lets a smaller team do more.",
  },
  layoffs: {
    title: "Layoffs / hiring freeze",
    qualify: "Workforce reductions or a hiring freeze. Distinguish the two in the detail. Cuts to planning/analytics/merchandising teams are an automation opportunity; broad cuts are a budget risk.",
    iaProducts: ["Agentic Retail Automation", "InventorySmart", "ForecastSmart"],
    soWhatHint: "Planning-team cuts → lead with automation. Broad cuts → treat as budget risk, time carefully.",
  },
  budget_cuts: {
    title: "Budget cuts",
    qualify: "Cost or capex reduction, or margin pressure.",
    iaProducts: ["MarkSmart", "PriceSmart"],
    soWhatHint: "Frame IA as margin recovery, not new spend. Lead with markdown and pricing ROI.",
  },
  facility_closures: {
    title: "Facility / store closures",
    qualify: "Store, DC or facility closures. Fleet rationalization forces inventory redistribution and re-forecasting.",
    iaProducts: ["InventorySmart", "ForecastSmart"],
    soWhatHint: "Closures scramble the allocation model. Lead with re-forecasting and redistribution.",
  },
  procurement_freeze: {
    title: "Procurement freeze",
    qualify: "A pause on new vendor contracts or procurement.",
    iaProducts: [],
    soWhatHint: "Timing signal — don't waste a cycle now; note the thaw date and re-engage.",
  },
  debt_restructuring: {
    title: "Debt restructuring",
    qualify: "Distressed refinancing, covenant relief, or debt restructuring. Working-capital pressure.",
    iaProducts: ["InventorySmart", "MarkSmart"],
    soWhatHint: "Working-capital pressure makes inventory-reduction ROI the lead argument.",
  },
  banner_selloff: {
    title: "Brand / banner sell-off",
    qualify: "A divestiture or spin-off of a brand or banner, re-architecting the planning hierarchy.",
    iaProducts: ["PlanSmart", "AssortSmart"],
    soWhatHint: "Divestiture re-architects the planning hierarchy. Lead with re-basing PlanSmart/AssortSmart.",
  },
  rival_tool_purchase: {
    title: "Recent rival tool purchase",
    qualify: "A COMPETITORS vendor signed or deployed. Capture the vendor name and date so a displacement play can be timed at renewal.",
    iaProducts: ["PlanSmart", "ForecastSmart", "PriceSmart"],
    soWhatHint: "They just bought a rival. Note vendor + date; time a displacement play at renewal.",
  },
};

// ── SEARCH ──────────────────────────────────────────────────────────────────────
// A small set of BROAD queries feeds one pooled result set; the LLM classifier
// then judges every search-derived signal from that pool (quota-efficient AND
// more accurate than one narrow query per signal). {company}/{domain} interpolated.
export const BROAD_QUERIES: string[] = [
  // 1. General recent retail news about the exact company.
  '"{company}" (retail OR retailer OR merchandising OR stores OR inventory OR ecommerce) news',
  // 2. Leadership moves in ICP functions.
  '"{company}" (appoints OR names OR hires OR "steps down" OR promoted) (CEO OR "Chief Merchandising" OR "Chief Merchant" OR CIO OR CTO OR "Chief Supply Chain" OR "Chief Digital" OR "Chief Data" OR "VP Planning" OR GMM OR DMM)',
  // 3. Operational pain — inventory and price failures.
  '"{company}" (inventory OR markdown OR stockout OR overstock OR "sell-through" OR "margin" OR "forecast accuracy" OR shrink OR "excess inventory" OR write-down)',
  // 4. Growth / structural change.
  '"{company}" (acquires OR merger OR "new stores" OR "distribution center" OR "expands into" OR "private label" OR "new category" OR RFP OR divestiture OR "sells" OR "spin-off")',
  // 5. Incumbent vendors, tech migrations and distress.
  '"{company}" (RELEX OR "o9" OR "Blue Yonder" OR "Oracle Retail" OR SAP OR "Manhattan Associates" OR Snowflake OR Databricks OR Aptos OR Logility OR layoffs OR "cost cutting" OR restructuring OR bankruptcy OR "procurement freeze" OR debt)',
  // 6. Authoritative PR wires — real, dated corporate announcements.
  '"{company}" (announces OR appoints OR acquires OR expands OR launches OR selects OR opens) (site:businesswire.com OR site:prnewswire.com OR site:globenewswire.com)',
  // 7. Retail trade press — high-signal industry coverage.
  '"{company}" (site:retaildive.com OR site:wwd.com OR site:chainstoreage.com OR site:sourcingjournal.com OR site:modernretail.co OR site:footwearnews.com)',
  // 8. The company's own newsroom / investor relations.
  'site:{domain} (press OR news OR announces OR investor OR "news release" OR earnings)',
];

// Reddit-specific query for operational-pain complaints (via the search backend,
// site-scoped, plus a direct Reddit JSON fetch in reddit-provider.ts).
export const REDDIT_QUERY = 'site:reddit.com "{company}" (inventory OR stockout OR "out of stock" OR markdown OR "poor quality" OR complaint OR "never in stock")';

export function fillQuery(template: string, company: string, domain: string): string {
  return template.replaceAll("{company}", company).replaceAll("{domain}", domain);
}

// Deterministic keyword gates (fallback classifier when no Anthropic key). Applied
// to a result's title+snippet; `must` = at least one required, `reject` disqualifies.
export interface NewsSearchConfig {
  must: string[];
  reject?: string[];
}

export const NEWS_SEARCH: Partial<Record<CatalogId, NewsSearchConfig>> = {
  rfp_rfq_rfi: { must: ["rfp", "rfi", "rfq", "request for proposal", "request for information"], reject: ["construction", "facilities", "staffing", "media buying", "carrier"] },
  ma_activity: { must: ["acquir", "merger", "majority stake", "buyout", "takeover"] },
  geographic_expansion: { must: ["new store", "distribution center", "fulfillment center", "expands into", "enters the", "new market", "new region", "opens in"], reject: ["pop-up", "temporary", "seasonal"] },
  operational_pain: { must: ["stockout", "out of stock", "overstock", "excess inventory", "write-down", "markdown", "margin", "sell-through", "forecast accuracy", "allocation", "aged inventory", "shrink"], reject: ["data breach", "lawsuit", "recall", "food safety", "esg"] },
  leadership_change: { must: ["appoint", "names", "hire", "joins", "new chief", "new vp", "promoted", "steps down"], reject: ["former", "chro", "chief people", "general counsel", "communications", "sustainability"] },
  erp_crm_migration: { must: ["implement", "migrat", "deploy", "rolling out", "selects", "goes live", "standing up", "s/4hana", "snowflake", "databricks"], reject: ["partnership", "integration announcement"] },
  bankruptcy: { must: ["chapter 11", "bankruptcy", "insolvency", "administration", "files for"] },
  store_expansion: { must: ["new store", "distribution center", "fulfillment center", "new dc", "opens", "expansion"], reject: ["closing", "closure"] },
  vendor_sentiment: { must: ["relex", "o9", "blue yonder", "oracle retail", "jda", "aptos", "logility", "manhattan", "sap"], reject: [] },
  new_product_line: { must: ["new category", "private label", "new brand", "product line", "launches"] },
  layoffs: { must: ["layoff", "job cut", "hiring freeze", "workforce reduction", "lays off", "let go"] },
  budget_cuts: { must: ["cost reduction", "cost cutting", "cutting costs", "capex", "margin pressure", "expense reduction", "austerity"] },
  facility_closures: { must: ["clos", "shut", "rationaliz", "consolidat"], reject: ["opening", "new store"] },
  procurement_freeze: { must: ["procurement freeze", "vendor freeze", "spending freeze", "pause new contracts"] },
  debt_restructuring: { must: ["debt restructuring", "refinanc", "covenant", "distressed", "creditors"] },
  banner_selloff: { must: ["divestiture", "sells", "spin-off", "spinoff", "sell-off", "carve-out"] },
  rival_tool_purchase: { must: ["relex", "o9", "blue yonder", "oracle retail", "aptos", "logility", "manhattan", "selects", "implements", "deploys"] },
};

// The signals sourced from search (everything except tech-stack (homepage) and hiring (jobs)).
export const SEARCH_SIGNAL_IDS = Object.keys(NEWS_SEARCH) as CatalogId[];

// ── CLASSIFIER GUIDANCE ─────────────────────────────────────────────────────────
export function domainGuard(company: string, domain: string, industry?: string | null): string {
  return [
    `IDENTITY GUARD — be strict about company identity:`,
    `- The ONE target is ${company}, the company operating the website ${domain}${industry ? ` in the ${industry} industry` : ""}.`,
    `- Reject any result about a DIFFERENT company that merely shares the name or part of the`,
    `  name "${company}" but operates a different website or a different industry (namesakes,`,
    `  unrelated brands, holding companies with a similar name).`,
    `- Reject any result where "${company}" appears only as a common word, a generic phrase,`,
    `  or an unrelated context rather than a reference to this specific company.`,
    `- If you cannot confirm a result is about THIS exact company, treat it as not about them.`,
  ].join("\n");
}

export function criteriaBlock(ids: CatalogId[]): string {
  return ids
    .map((id) => {
      const c = ICP_CRITERIA[id];
      const reject = c.reject ? ` REJECT: ${c.reject}` : "";
      return `- ${id} (${c.title}): ${c.qualify}${reject}`;
    })
    .join("\n");
}

export function productConstraint(): string {
  return `When you set iaProducts, choose ONLY from this exact list and never invent a name: ${ALL_PRODUCT_NAMES.join(", ")}.`;
}
