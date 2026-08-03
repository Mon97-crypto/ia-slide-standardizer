/**
 * scan-contract.ts — the canonical wire contract shared by client and server.
 *
 * The CATALOG below is the single source of truth for signal ids, types and
 * weights. Edge functions NEVER compute scores; they return raw Signal objects
 * and the frontend adds score_contribution + weight by looking these up.
 *
 * NOTE: these ids are canonical. icp.ts layers relevance *criteria* and
 * vocabulary on top of them but never renames them.
 */

export type SignalType = "positive" | "negative" | "neutral";

export interface Evidence {
  title: string;
  url: string;
  date: string;
}

/** The exact shape every edge function returns (an array of these, nothing else). */
export interface Signal {
  name: CatalogId | string; // an id from the catalog
  type: SignalType;
  found: boolean;
  detail: string; // one short human sentence
  evidence: Evidence[]; // max 5
  /** ICP enrichment, populated by the classifier where relevant. */
  iaProducts?: string[];
  soWhat?: string;
}

/** A Signal after the frontend has scored and enriched it from the catalog. */
export interface ScoredSignal extends Signal {
  type: SignalType;
  weight: number;
  score_contribution: number;
  /** Human-facing group + display label pulled from the catalog. */
  label: string;
  glyph: string;
}

/** The uniform envelope every function returns. Never throws. */
export interface FunctionResult {
  ok: boolean;
  signals: Signal[];
  meta?: Record<string, unknown>;
  error?: string;
}

interface CatalogEntry {
  type: SignalType;
  weight: number;
  /** Salesperson-facing name, sentence case. */
  label: string;
  /** Non-color cue so rows read in grayscale and for colorblind users. */
  glyph: string;
}

// ── CATALOG — canonical ids, types and weights. Never invent new ids. ──────────
export const CATALOG = {
  // positive
  rfp_rfq_rfi: { type: "positive", weight: 25, label: "RFP, RFQ or RFI", glyph: "◆" },
  erp_crm_migration: { type: "positive", weight: 20, label: "ERP, CRM or platform migration", glyph: "▲" },
  leadership_change: { type: "positive", weight: 15, label: "Leadership change", glyph: "◆" },
  ma_activity: { type: "positive", weight: 12, label: "Mergers and acquisitions", glyph: "▲" },
  operational_pain: { type: "positive", weight: 10, label: "Operational pain", glyph: "◆" },
  hiring_activity: { type: "positive", weight: 8, label: "Relevant hiring", glyph: "▲" },
  geographic_expansion: { type: "positive", weight: 5, label: "Geographic expansion", glyph: "▲" },
  tech_stack_change: { type: "positive", weight: 3, label: "Modern tech stack", glyph: "▲" },
  ipo_preparation: { type: "positive", weight: 2, label: "IPO preparation", glyph: "▲" },
  // negative
  bankruptcy: { type: "negative", weight: 45, label: "Bankruptcy", glyph: "▼" },
  layoffs: { type: "negative", weight: 25, label: "Layoffs or hiring freeze", glyph: "▽" },
  budget_cuts: { type: "negative", weight: 15, label: "Budget cuts", glyph: "▽" },
  facility_closures: { type: "negative", weight: 10, label: "Facility or store closures", glyph: "▽" },
  no_job_openings: { type: "negative", weight: 5, label: "No relevant job openings", glyph: "▽" },
  // neutral (display only, never scored)
  reorganization: { type: "neutral", weight: 55, label: "Reorganization", glyph: "○" },
  internal_promotion: { type: "neutral", weight: 45, label: "Internal promotion", glyph: "○" },
} as const satisfies Record<string, CatalogEntry>;

export type CatalogId = keyof typeof CATALOG;

export const CATALOG_IDS = Object.keys(CATALOG) as CatalogId[];

export function isCatalogId(name: string): name is CatalogId {
  return Object.prototype.hasOwnProperty.call(CATALOG, name);
}

// ── SCORING (frontend only) ────────────────────────────────────────────────────
export function contributionFor(signal: Signal): number {
  if (!signal.found || !isCatalogId(signal.name)) return 0;
  const entry = CATALOG[signal.name];
  if (entry.type === "positive") return entry.weight;
  if (entry.type === "negative") return -entry.weight;
  return 0; // neutral is display only
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

/** Enrich a raw Signal with catalog-derived type, weight, contribution and labels. */
export function scoreSignal(signal: Signal): ScoredSignal {
  const entry = isCatalogId(signal.name) ? CATALOG[signal.name] : undefined;
  return {
    ...signal,
    type: entry?.type ?? signal.type,
    weight: entry?.weight ?? 0,
    score_contribution: contributionFor(signal),
    label: entry?.label ?? signal.name,
    glyph: entry?.glyph ?? "○",
  };
}
