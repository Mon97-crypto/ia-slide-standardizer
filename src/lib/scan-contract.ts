/**
 * scan-contract.ts — the canonical wire contract shared by client and server.
 *
 * The CATALOG below is the single source of truth for signal ids, types,
 * weights, display labels, and their GROUP ("key" | "supporting"). These 19
 * signals are the only ones the product considers or displays.
 *
 * Edge functions never compute scores; they return raw Signal objects and the
 * frontend adds score_contribution + weight from this catalog.
 *
 * icp.ts layers relevance CRITERIA and search vocabulary onto these ids; it
 * never renames them.
 */

export type SignalType = "positive" | "negative" | "neutral";
export type SignalGroup = "key" | "supporting";

export interface Evidence {
  title: string;
  url: string;
  date: string;
}

export interface Signal {
  name: CatalogId | string;
  type: SignalType;
  found: boolean;
  detail: string;
  evidence: Evidence[];
  iaProducts?: string[];
  soWhat?: string;
}

export interface ScoredSignal extends Signal {
  type: SignalType;
  weight: number;
  score_contribution: number;
  label: string;
  glyph: string;
  group: SignalGroup;
}

export interface FunctionResult {
  ok: boolean;
  signals: Signal[];
  meta?: Record<string, unknown>;
  error?: string;
}

interface CatalogEntry {
  type: SignalType;
  weight: number;
  label: string;
  glyph: string;
  group: SignalGroup;
}

// ── CATALOG — 19 signals, in display order within each group. ───────────────────
// KEY signals come first (higher-value buying triggers), then SUPPORTING.
export const CATALOG = {
  // ── KEY SIGNALS ──────────────────────────────────────────────────────────────
  tech_stack_change: { type: "positive", weight: 5, label: "Current tech stack", glyph: "▲", group: "key" },
  rfp_rfq_rfi: { type: "positive", weight: 25, label: "RFP, RFQ or RFI", glyph: "◆", group: "key" },
  ma_activity: { type: "positive", weight: 15, label: "M&A activity", glyph: "▲", group: "key" },
  geographic_expansion: { type: "positive", weight: 10, label: "Geographic expansion", glyph: "▲", group: "key" },
  operational_pain: { type: "positive", weight: 25, label: "Operational pain", glyph: "◆", group: "key" },
  leadership_change: { type: "positive", weight: 15, label: "Leadership changes", glyph: "◆", group: "key" },
  erp_crm_migration: { type: "positive", weight: 20, label: "ERP, CRM or cloud migration", glyph: "▲", group: "key" },
  bankruptcy: { type: "negative", weight: 45, label: "Bankruptcy", glyph: "▼", group: "key" },
  store_expansion: { type: "positive", weight: 10, label: "Stores / facility expansion", glyph: "▲", group: "key" },
  vendor_sentiment: { type: "positive", weight: 22, label: "Current vendor sentiment", glyph: "◆", group: "key" },

  // ── SUPPORTING SIGNALS ───────────────────────────────────────────────────────
  new_product_line: { type: "positive", weight: 6, label: "New product line", glyph: "▲", group: "supporting" },
  hiring_activity: { type: "positive", weight: 8, label: "Relevant hiring", glyph: "▲", group: "supporting" },
  layoffs: { type: "negative", weight: 15, label: "Layoffs / hiring freeze", glyph: "▽", group: "supporting" },
  budget_cuts: { type: "negative", weight: 12, label: "Budget cuts", glyph: "▽", group: "supporting" },
  facility_closures: { type: "negative", weight: 10, label: "Facility / store closures", glyph: "▽", group: "supporting" },
  procurement_freeze: { type: "negative", weight: 5, label: "Procurement freeze", glyph: "▽", group: "supporting" },
  debt_restructuring: { type: "positive", weight: 6, label: "Debt restructuring", glyph: "▲", group: "supporting" },
  banner_selloff: { type: "positive", weight: 6, label: "Brand / banner sell-off", glyph: "▲", group: "supporting" },
  rival_tool_purchase: { type: "positive", weight: 12, label: "Recent rival tool purchase", glyph: "◆", group: "supporting" },
} as const satisfies Record<string, CatalogEntry>;

export type CatalogId = keyof typeof CATALOG;

export const CATALOG_IDS = Object.keys(CATALOG) as CatalogId[];
export const KEY_SIGNALS = CATALOG_IDS.filter((id) => CATALOG[id].group === "key");
export const SUPPORTING_SIGNALS = CATALOG_IDS.filter((id) => CATALOG[id].group === "supporting");

export function isCatalogId(name: string): name is CatalogId {
  return Object.prototype.hasOwnProperty.call(CATALOG, name);
}

// ── SCORING (frontend only) ─────────────────────────────────────────────────────
export function contributionFor(signal: Signal): number {
  if (!signal.found || !isCatalogId(signal.name)) return 0;
  const entry = CATALOG[signal.name];
  if (entry.type === "positive") return entry.weight;
  if (entry.type === "negative") return -entry.weight;
  return 0;
}

export type IntentLevel =
  | "Disqualified"
  | "Strong buyer"
  | "Potential buyer"
  | "Poor fit"
  | "Neutral";

export function intentFor(total: number, bankruptcyFound: boolean): IntentLevel {
  if (bankruptcyFound || total <= -50) return "Disqualified";
  if (total >= 30) return "Strong buyer";
  if (total >= 10) return "Potential buyer";
  if (total <= -10) return "Poor fit";
  return "Neutral";
}

export function scoreSignal(signal: Signal): ScoredSignal {
  const entry = isCatalogId(signal.name) ? CATALOG[signal.name] : undefined;
  return {
    ...signal,
    type: entry?.type ?? signal.type,
    weight: entry?.weight ?? 0,
    score_contribution: contributionFor(signal),
    label: entry?.label ?? signal.name,
    glyph: entry?.glyph ?? "○",
    group: entry?.group ?? "supporting",
  };
}
