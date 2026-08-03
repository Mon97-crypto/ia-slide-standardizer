/**
 * scan.ts — client-side orchestration.
 *
 * runScan calls the three functions IN PARALLEL with Promise.allSettled, never
 * sequentially. Each settles independently and fires onStep. It then merges the
 * three signal arrays, fills gaps against the catalog, scores every signal and
 * computes the intent level per the contract.
 */

import {
  CATALOG,
  CATALOG_IDS,
  intentFor,
  scoreSignal,
  type CatalogId,
  type FunctionResult,
  type ScoredSignal,
  type Signal,
} from "./scan-contract";

// Re-export the types the UI consumes so components import from one module.
export type { ScoredSignal, IntentLevel, Signal, CatalogId } from "./scan-contract";

export type StepKey = "edgar" | "techstack" | "news";
export type StepStatus = "pending" | "done" | "failed";

export interface StepUpdate {
  key: StepKey;
  status: StepStatus;
  foundCount?: number;
  label: string;
}

const STEP_LABELS: Record<StepKey, string> = {
  edgar: "SEC filings",
  techstack: "Tech stack",
  news: "News and hiring",
};

/** Which catalog ids each function is responsible for — used to skip functions
 *  when the caller has deselected all of a function's signals. */
export const FUNCTION_SIGNALS: Record<StepKey, CatalogId[]> = {
  edgar: ["bankruptcy", "reorganization", "ma_activity", "ipo_preparation"],
  techstack: ["tech_stack_change"],
  news: [
    "leadership_change",
    "erp_crm_migration",
    "operational_pain",
    "geographic_expansion",
    "hiring_activity",
    "layoffs",
    "budget_cuts",
    "facility_closures",
    "rfp_rfq_rfi",
    "internal_promotion",
    "no_job_openings",
  ],
};

const ENDPOINT: Record<StepKey, string> = {
  edgar: "/api/public/scan-edgar",
  techstack: "/api/public/scan-techstack",
  news: "/api/public/scan-news",
};

export interface RunScanArgs {
  company: string;
  domain: string;
  /** Optional filter — only run functions with at least one selected signal. */
  signals?: CatalogId[];
  onStep?: (u: StepUpdate) => void;
  /** Force a re-run past the 24h cache. */
  refresh?: boolean;
  signal?: AbortSignal;
}

export interface ScanResult {
  company: string;
  domain: string;
  signals: ScoredSignal[];
  total: number;
  intent: ReturnType<typeof intentFor>;
  verified: boolean;
  resolvedName?: string;
  /** Steps that failed, so the UI can name what was skipped. */
  failedSteps: StepKey[];
  cached: boolean;
  cachedAt?: string;
}

async function callFunction(
  key: StepKey,
  args: RunScanArgs,
): Promise<FunctionResult> {
  const timeout = key === "news" ? 90_000 : 20_000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const onAbort = () => controller.abort();
  args.signal?.addEventListener("abort", onAbort);
  try {
    const res = await fetch(ENDPOINT[key], {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ company: args.company, domain: args.domain }),
      signal: controller.signal,
    });
    if (!res.ok) {
      return { ok: false, signals: [], error: `HTTP ${res.status}` };
    }
    return (await res.json()) as FunctionResult;
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  } finally {
    clearTimeout(timer);
    args.signal?.removeEventListener("abort", onAbort);
  }
}

function shouldRun(key: StepKey, filter?: CatalogId[]): boolean {
  if (!filter || filter.length === 0) return true;
  return FUNCTION_SIGNALS[key].some((id) => filter.includes(id));
}

export async function runScan(args: RunScanArgs): Promise<ScanResult> {
  const { company, domain, signals: filter, onStep } = args;

  // 1. 24h cache read, unless refresh was requested.
  if (!args.refresh) {
    try {
      const res = await fetch(
        `/api/public/scan-cache?domain=${encodeURIComponent(domain)}`,
        { signal: args.signal },
      );
      if (res.ok) {
        const cached = (await res.json()) as { hit: boolean; result?: ScanResult };
        if (cached.hit && cached.result) {
          return { ...cached.result, cached: true };
        }
      }
    } catch {
      // cache is best-effort; fall through to a live scan.
    }
  }

  const activeKeys = (Object.keys(ENDPOINT) as StepKey[]).filter((k) =>
    shouldRun(k, filter),
  );

  activeKeys.forEach((key) =>
    onStep?.({ key, status: "pending", label: STEP_LABELS[key] }),
  );

  const settled = await Promise.allSettled(
    activeKeys.map(async (key) => {
      const result = await callFunction(key, args);
      const foundCount = result.signals.filter((s) => s.found).length;
      onStep?.({
        key,
        status: result.ok ? "done" : "failed",
        foundCount,
        label: STEP_LABELS[key],
      });
      return { key, result };
    }),
  );

  const merged: Signal[] = [];
  const failedSteps: StepKey[] = [];
  let verified = true;
  let resolvedName: string | undefined;

  for (const outcome of settled) {
    if (outcome.status !== "fulfilled") continue;
    const { key, result } = outcome.value;
    if (!result.ok) failedSteps.push(key);
    if (result.meta && typeof result.meta.verified === "boolean") {
      if (result.meta.verified === false) verified = false;
      if (typeof result.meta.resolvedName === "string") {
        resolvedName = result.meta.resolvedName;
      }
    }
    merged.push(...result.signals);
  }

  // 3. Fill gaps: any catalog id not returned by any function is found:false.
  const present = new Set(merged.map((s) => s.name));
  for (const id of CATALOG_IDS) {
    if (!present.has(id)) {
      merged.push({
        name: id,
        type: CATALOG[id].type,
        found: false,
        detail: "Not checked",
        evidence: [],
      });
    }
  }

  const scored = merged.map(scoreSignal);
  const total = scored.reduce((sum, s) => sum + s.score_contribution, 0);
  const bankruptcyFound = scored.some((s) => s.name === "bankruptcy" && s.found);
  const intent = intentFor(total, bankruptcyFound);

  const result: ScanResult = {
    company,
    domain,
    signals: sortSignals(scored),
    total,
    intent,
    verified,
    resolvedName,
    failedSteps,
    cached: false,
    cachedAt: undefined,
  };

  // Persist to the 24h cache (best-effort, fire and forget).
  if (verified) {
    void fetch("/api/public/scan-cache", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ domain, company, result }),
    }).catch(() => {});
  }

  return result;
}

/** Found signals first, then by absolute contribution, then neutral, then unchecked. */
export function sortSignals(signals: ScoredSignal[]): ScoredSignal[] {
  return [...signals].sort((a, b) => {
    if (a.found !== b.found) return a.found ? -1 : 1;
    const am = Math.abs(a.score_contribution);
    const bm = Math.abs(b.score_contribution);
    if (am !== bm) return bm - am;
    return b.weight - a.weight;
  });
}
