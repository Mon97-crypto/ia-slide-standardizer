/**
 * icp.ts — Impact Analytics ideal-customer-profile vocabulary.
 *
 * This is the file we tune over time. Everything that decides whether a signal
 * is "relevant to what Impact Analytics can sell into" lives here, so endpoints
 * and the classifier import from one place instead of duplicating strings.
 *
 * Impact Analytics is an AI-native retail decisioning platform. The scanner's
 * job is not "is anything happening at this company" but "is anything happening
 * that Impact Analytics can sell into." A new CHRO and a new Chief Merchant do
 * not score the same, because only one of them buys retail planning software.
 *
 * NOTE: catalog signal ids live in scan-contract.ts and are canonical. This
 * module attaches relevance CRITERIA and vocabulary to those ids; it never
 * renames them.
 */

import type { CatalogId } from "./scan-contract";

// ── PRODUCT PORTFOLIO — five pillars ────────────────────────────────────────────
// Used to constrain the classifier's iaProducts field so it cannot invent names.
export const IA_PRODUCTS = {
  merchandising: [
    "PlanSmart", // merchandise financial planning, open-to-buy
    "ItemSmart", // item planning
    "AssortSmart", // assortment planning
    "SizeSmart", // size curves
    "StoreSmart", // store execution
    "VisualSmart", // visual line planning
  ],
  inventoryReplenishment: [
    "ForecastSmart", // demand planning / forecasting
    "InventorySmart", // planning, allocation & replenishment
    "SpaceSmart", // space planning
  ],
  pricingPromotions: [
    "PriceSmart", // lifecycle pricing
    "MarkSmart", // markdown optimization
    "BaseSmart", // dynamic / everyday pricing
    "PromoSmart", // promotion planning
    "TradeSmart", // trade promotion management
  ],
  dataIntelligence: [
    "MondaySmart", // BI
    "TestSmart", // test & learn
    "AttributeSmart", // product tagging / attribution
    "DataSmart", // data lineage
  ],
  agenticServices: [
    "Platform Agents",
    "Agentic Retail Automation",
    "CortexEye",
    "Data Engineering",
    "Retail Analytics",
    "Pricing War Room",
    "Sizing as a Service",
  ],
} as const;

/** Flat list of every valid product name, for validating classifier output. */
export const ALL_PRODUCT_NAMES: string[] = Object.values(IA_PRODUCTS).flat();
/** lowercased name → canonical name, so we can match case-insensitively. */
const PRODUCT_LOOKUP = new Map(ALL_PRODUCT_NAMES.map((p) => [p.toLowerCase(), p]));

/** Keep only real IA product names; drop anything the model invented. */
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
  "retail — apparel, footwear and accessories",
  "retail — grocery",
  "retail — specialty",
  "retail — department store",
  "retail — furniture",
  "retail — electronics and appliances",
  "retail — home improvement",
  "CPG and OTC manufacturing",
  "wholesale and distribution",
  "quick-service restaurants",
] as const;

// ── COMPETITORS — incumbent presence is our strongest buying signal ──────────────
// Dissatisfaction, non-renewal or a failed implementation at any of these is a
// displacement opening. "Excel-based planning" / "manual planning" is a
// legacy-displacement signal in its own right (see LEGACY_PLANNING_TERMS).
export const COMPETITORS = [
  "RELEX",
  "o9 Solutions",
  "Blue Yonder", // formerly JDA
  "JDA",
  "Oracle Retail",
  "SAP", // incl. S/4HANA and CAR
  "Aptos",
  "Anaplan",
  "Invent Analytics",
  "First Insight",
  "Revionics",
  "Zilliant",
  "PROS",
  "ToolsGroup",
  "Logility",
  "Kinaxis",
  "Manhattan Associates",
  "Symphony RetailAI",
  "Antuit.ai",
  "Increff",
  "7thonline",
  "NielsenIQ",
  "Circana",
  "SAS",
] as const;

/** Legacy / manual planning tells — a displacement signal on their own. */
export const LEGACY_PLANNING_TERMS = [
  "Excel-based planning",
  "spreadsheet planning",
  "manual planning",
  "manual forecasting",
  "manual allocation",
];

// ── PER-SIGNAL QUALIFYING CRITERIA ──────────────────────────────────────────────
// Each entry drives both the classifier prompt and (for SERP-style endpoints) the
// query vocabulary. `qualify` = what must be true to fire; `reject` = look-alikes
// that must NOT fire; `iaProducts` = the opening this signal creates; `soWhatHint`
// = the lead a rep should use.

export interface IcpCriteria {
  /** Salesperson-facing label for the criteria (mirrors catalog where useful). */
  title: string;
  qualify: string;
  reject?: string;
  iaProducts: string[];
  soWhatHint: string;
}

export const ICP_CRITERIA: Record<CatalogId, IcpCriteria> = {
  rfp_rfq_rfi: {
    title: "RFP, RFQ or RFI",
    qualify:
      "A public RFP, RFQ or RFI for retail planning, merchandising, forecasting, assortment, pricing, promotion, markdown, inventory or allocation, space planning, attribution, retail BI or a data platform.",
    reject:
      "Construction, facilities, legal panels, staffing, media buying or carrier and logistics RFPs.",
    iaProducts: ["PlanSmart", "AssortSmart", "ForecastSmart", "PriceSmart", "InventorySmart"],
    soWhatHint: "An active buying process is open. Lead with a direct response to the stated scope.",
  },
  erp_crm_migration: {
    title: "ERP, CRM or cloud and data migration",
    qualify:
      "An active migration with a change verb (implementing, migrating, deploying, replacing, rolling out). Highest value: SAP S/4HANA, Oracle Retail or Fusion, Blue Yonder, Manhattan, NetSuite, Microsoft Dynamics, and data-platform moves to Snowflake, Databricks or BigQuery.",
    reject:
      "Generic 'digital transformation' press releases, vendor marketing pages naming no system, or a partnership or integration announcement.",
    iaProducts: ["DataSmart", "ForecastSmart", "InventorySmart", "PlanSmart", "Platform Agents"],
    soWhatHint:
      "A company standing up a modern data platform is exactly who can deploy IA next. Lead with time-to-value on top of the new stack.",
  },
  leadership_change: {
    title: "Leadership change",
    qualify:
      "A newly appointed ICP-adjacent leader: Chief Merchandising Officer or Chief Merchant, GMM, DMM, Chief Supply Chain Officer, COO, CIO, CTO, Chief Digital Officer, Chief Data or Analytics Officer, CFO, Chief Stores Officer, or VP of Planning, Allocation, Merchandising, Pricing, Demand Planning, Inventory or Retail Technology.",
    reject:
      "CHRO, Chief People Officer, General Counsel, brand or advertising CMO, Chief Communications Officer, Chief Sustainability Officer, and any article about a FORMER employee or alumnus.",
    iaProducts: ["PlanSmart", "AssortSmart", "ForecastSmart", "PriceSmart"],
    soWhatHint:
      "New leaders re-evaluate the stack in their first two quarters. Lead with a quick win in their function.",
  },
  ma_activity: {
    title: "Mergers and acquisitions",
    qualify:
      "A merger, acquisition or majority investment. Note whether the deal adds banners or categories — multi-banner complexity forces assortment rationalization and planning-system consolidation.",
    reject: "Rumor or analyst speculation with no confirmed transaction.",
    iaProducts: ["PlanSmart", "AssortSmart", "ItemSmart"],
    soWhatHint:
      "Integration forces banner and category consolidation. Lead with a single planning hierarchy across the combined estate.",
  },
  operational_pain: {
    title: "Operational pain",
    qualify:
      "A confirmed inventory or price problem: stockouts, low on-shelf availability, overstock, excess or aged inventory, inventory write-downs, heavy or unplanned markdowns, margin erosion, forecast-accuracy misses, allocation errors, size or fit problems, high return rates, poor sell-through, shrink, or supply-chain delays showing up as misplaced inventory.",
    reject:
      "Data breaches, employment lawsuits, food-safety recalls, ESG criticism, and service complaints unrelated to inventory or price. Vague 'challenges' do not qualify.",
    iaProducts: ["ForecastSmart", "InventorySmart", "MarkSmart", "SizeSmart", "PriceSmart"],
    soWhatHint:
      "This is the highest-value signal. Lead with the named pain and the product that fixes it, with a quantified ROI.",
  },
  hiring_activity: {
    title: "Relevant hiring",
    qualify:
      "Open roles in planning, allocation, replenishment, inventory, pricing, markdown, promotions, category management, space or assortment planning, buying and planning, retail data science, or analytics and data engineering in a merchandising or supply-chain context. A cluster of planning-team hires is a stronger signal than a single role. If a job description names a competitor tool, capture that tool as evidence.",
    reject:
      "Store associates, cashiers, warehouse pickers, drivers, security, marketing, and HR roles.",
    iaProducts: ["PlanSmart", "InventorySmart", "ForecastSmart", "Retail Analytics"],
    soWhatHint:
      "They are building a planning team by hand. Lead with automation that lets a smaller team do more.",
  },
  geographic_expansion: {
    title: "Geographic or store expansion",
    qualify:
      "Entry into a new country, region or market, or new stores, distribution centres or fulfilment centres. New demand curves, localized assortments and different size curves; more nodes make allocation harder.",
    reject: "A single pop-up or a temporary seasonal location.",
    iaProducts: ["ForecastSmart", "AssortSmart", "SizeSmart", "InventorySmart", "StoreSmart", "SpaceSmart"],
    soWhatHint:
      "New geography means new demand curves the current model has never seen. Lead with localized forecasting and assortment.",
  },
  tech_stack_change: {
    title: "Modern tech stack",
    qualify:
      "A modern, API-friendly web and cloud stack (React, Angular, Vue, AWS) rather than legacy CMS. Signals readiness to integrate a modern decisioning platform.",
    reject: "Legacy-only stacks with no modern tooling detected.",
    iaProducts: ["Platform Agents", "DataSmart"],
    soWhatHint: "The plumbing supports a fast integration. Use as a supporting, not a lead, signal.",
  },
  ipo_preparation: {
    title: "IPO preparation",
    qualify: "An S-1 filing or confirmed IPO process. Growth and margin scrutiny ahead.",
    reject: "Secondary offerings by an already-public company.",
    iaProducts: ["PriceSmart", "MarkSmart", "PlanSmart"],
    soWhatHint: "Pre-IPO scrutiny rewards margin discipline. Lead with pricing and markdown ROI.",
  },
  bankruptcy: {
    title: "Bankruptcy",
    qualify:
      "Chapter 11, administration or insolvency filing. Likely disqualifies a near-term purchase, but note that emergence from restructuring is a replatforming window.",
    iaProducts: ["InventorySmart", "MarkSmart"],
    soWhatHint:
      "Near-term risk, but watch for emergence — restructuring exits replatform. Hold and re-engage on emergence.",
  },
  layoffs: {
    title: "Layoffs or hiring freeze",
    qualify:
      "Workforce reductions or a hiring freeze. Distinguish the two in the detail line. Cuts to planning, analytics or merchandising teams are an automation opportunity; broad corporate cuts are a budget risk.",
    iaProducts: ["Agentic Retail Automation", "InventorySmart", "ForecastSmart"],
    soWhatHint:
      "If planning teams were cut, lead with automation. If cuts are broad, treat as a budget risk and time carefully.",
  },
  budget_cuts: {
    title: "Budget cuts",
    qualify: "Cost or capex reduction, or margin pressure.",
    iaProducts: ["MarkSmart", "PriceSmart"],
    soWhatHint:
      "Frame IA as margin recovery, not new spend. Lead with markdown and pricing ROI that pays for itself.",
  },
  facility_closures: {
    title: "Facility or store closures",
    qualify:
      "Store, distribution-centre or facility closures. Fleet rationalization forces inventory redistribution and re-forecasting.",
    iaProducts: ["InventorySmart", "ForecastSmart"],
    soWhatHint:
      "Closures scramble the allocation model. Lead with re-forecasting and inventory redistribution across the smaller fleet.",
  },
  no_job_openings: {
    title: "No relevant job openings",
    qualify:
      "An active search found no current planning, merchandising or analytics postings. Only true when you actively searched and found none.",
    iaProducts: [],
    soWhatHint: "No hiring in-function. A weak negative — deprioritize unless other signals fire.",
  },
  reorganization: {
    title: "Reorganization",
    qualify: "A restructuring or reorg announcement. Display only, never scored.",
    iaProducts: ["PlanSmart", "AssortSmart"],
    soWhatHint: "Context only. A reorg can reset the planning hierarchy — watch for follow-on signals.",
  },
  internal_promotion: {
    title: "Internal promotion",
    qualify: "An internal promotion into an ICP-adjacent role. Display only, never scored.",
    iaProducts: [],
    soWhatHint: "Context only. An internal promotion warms an existing relationship.",
  },
};

// ── SERP / SEARCH QUERY GROUPS ──────────────────────────────────────────────────
// Retail-planning vocabulary so queries return ICP-relevant hits, not generic
// business news. Total query count is kept roughly flat to stay inside quota.
// `{company}` and `{domain}` are interpolated by the caller.

export interface QueryGroup {
  signal: CatalogId | "vendor_sentiment" | "new_product_line";
  queries: string[];
}

export const queryGroups: QueryGroup[] = [
  {
    signal: "operational_pain",
    queries: [
      '"{company}" (stockout OR overstock OR "excess inventory" OR "inventory write-down" OR markdown OR "margin erosion" OR "sell-through" OR shrink)',
      '"{company}" ("forecast accuracy" OR "allocation error" OR "return rate" OR "on-shelf availability")',
    ],
  },
  {
    signal: "leadership_change",
    queries: [
      '"{company}" (appoints OR names OR hires) ("Chief Merchandising Officer" OR "Chief Merchant" OR "Chief Supply Chain Officer" OR CIO OR CTO OR "Chief Data" OR "VP Planning" OR "VP Merchandising")',
    ],
  },
  {
    signal: "erp_crm_migration",
    queries: [
      '"{company}" (implementing OR migrating OR deploying OR "rolling out") ("S/4HANA" OR "Oracle Retail" OR "Blue Yonder" OR Manhattan OR Snowflake OR Databricks OR BigQuery OR NetSuite OR "Microsoft Dynamics")',
    ],
  },
  {
    signal: "vendor_sentiment",
    queries: [
      '"{company}" (RELEX OR "o9" OR "Blue Yonder" OR "Oracle Retail" OR JDA OR Aptos OR Logility OR "Manhattan Associates") (renewal OR replace OR "rip and replace" OR dissatisfied OR "failed implementation" OR frustration)',
    ],
  },
  {
    signal: "rfp_rfq_rfi",
    queries: [
      '"{company}" (RFP OR RFI OR RFQ) (planning OR merchandising OR forecasting OR assortment OR pricing OR "markdown" OR allocation OR "space planning")',
    ],
  },
  {
    signal: "geographic_expansion",
    queries: [
      '"{company}" ("new stores" OR "distribution center" OR "fulfillment center" OR "expands into" OR "enters the" OR "new market")',
    ],
  },
  {
    signal: "ma_activity",
    queries: [
      '"{company}" (acquires OR "to acquire" OR merger OR "acquisition of" OR "majority stake") (retail OR brand OR banner OR chain)',
    ],
  },
  {
    signal: "new_product_line",
    queries: [
      '"{company}" ("new category" OR "private label" OR "new brand" OR "product line" OR "launches")',
    ],
  },
  {
    signal: "hiring_activity",
    queries: [
      '"{company}" jobs ("demand planner" OR "merchandise planner" OR "allocation analyst" OR "inventory analyst" OR "pricing analyst" OR "category manager" OR "space planner")',
    ],
  },
  {
    signal: "layoffs",
    queries: [
      '"{company}" (layoffs OR "job cuts" OR "hiring freeze" OR "workforce reduction" OR restructuring)',
    ],
  },
];

/** Interpolate {company} / {domain} into a query template. */
export function fillQuery(template: string, company: string, domain: string): string {
  return template.replaceAll("{company}", company).replaceAll("{domain}", domain);
}

// ── CLASSIFIER GUIDANCE ─────────────────────────────────────────────────────────
// A reusable prompt fragment. Threads the domain through so we reject
// similarly-named companies (the fila.com / F.I.L.A. stationery bug).

export function domainGuard(company: string, domain: string): string {
  return (
    `The target company's website is ${domain}. Only report evidence about the company at that ` +
    `website. Reject results about similarly-named companies with a different website (for example, ` +
    `a company that merely shares part of the name "${company}").`
  );
}

/** Renders the per-signal qualifying rules for a set of catalog ids. */
export function criteriaBlock(ids: CatalogId[]): string {
  return ids
    .map((id) => {
      const c = ICP_CRITERIA[id];
      const reject = c.reject ? ` REJECT: ${c.reject}` : "";
      return `- ${id} (${c.title}): ${c.qualify}${reject}`;
    })
    .join("\n");
}

/** The IA product names the classifier is allowed to put in iaProducts. */
export function productConstraint(): string {
  return (
    `When you set iaProducts, choose ONLY from this exact list and never invent a name: ` +
    ALL_PRODUCT_NAMES.join(", ") +
    `.`
  );
}
