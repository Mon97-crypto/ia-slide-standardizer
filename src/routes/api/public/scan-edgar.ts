/**
 * scan-edgar.ts — SEC EDGAR signals. No API key required; the SEC APIs are free
 * and public. Accepts POST { company, domain } and returns the contract shape.
 *
 * Entity accuracy: the company is matched to its EXACT SEC registrant via the
 * official company_tickers registry (normalized-name match on the Apollo-resolved
 * official name), NOT fuzzy full-text search. If there is no confident registry
 * match the company is treated as private and no EDGAR signals are fired — this
 * prevents wrong-company filings (e.g. a namesake) from leaking in.
 *
 * Signals derived from 8-K item codes filed in the LAST 365 DAYS (item codes are
 * in the submissions JSON, so no filing-text fetch is needed):
 *   bankruptcy         : 8-K item 1.03
 *   ma_activity        : 8-K item 2.01, or DEFM14A / SC 13D / S-4
 *   leadership_change  : 8-K item 5.02 (departure/appointment of directors/officers)
 *   budget_cuts        : 8-K item 2.05 (costs of exit or disposal / restructuring)
 *   debt_restructuring : 8-K item 2.04 (acceleration of a financial obligation)
 */

import type { CatalogId, Evidence, FunctionResult, Signal } from "../../../lib/scan-contract";
import { padCik, secFetch } from "./_sec";
import { resolveEntity } from "./account-info";

interface ScanInput {
  company: string;
  domain: string;
}

// The catalog ids EDGAR can produce.
const EDGAR_IDS: CatalogId[] = ["bankruptcy", "ma_activity", "leadership_change", "budget_cuts", "debt_restructuring"];

const TYPE: Record<string, Signal["type"]> = {
  bankruptcy: "negative",
  ma_activity: "positive",
  leadership_change: "positive",
  budget_cuts: "negative",
  debt_restructuring: "positive",
};

// ── Exact registrant matching via the official SEC company registry ──────────────
interface TickerRow {
  cik_str: number;
  ticker: string;
  title: string;
}
let registryCache: { at: number; byName: Map<string, number> } | null = null;
const REGISTRY_TTL_MS = 24 * 60 * 60 * 1000;

function normalizeName(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[.,/#!$%^*;:{}=\-_`~()'"]/g, " ")
    .replace(/\b(the|inc|incorporated|corp|corporation|co|company|plc|ltd|limited|lp|llc|holdings|holding|group|sa|nv|ag|se)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

async function loadRegistry(): Promise<Map<string, number>> {
  if (registryCache && Date.now() - registryCache.at < REGISTRY_TTL_MS) return registryCache.byName;
  const byName = new Map<string, number>();
  try {
    const res = await secFetch("https://www.sec.gov/files/company_tickers.json");
    if (res.ok) {
      const data = (await res.json()) as Record<string, TickerRow>;
      for (const row of Object.values(data)) {
        if (!row?.title || !Number.isFinite(row.cik_str)) continue;
        const key = normalizeName(row.title);
        if (key && !byName.has(key)) byName.set(key, row.cik_str);
      }
    }
  } catch {
    // registry unavailable — caller falls back to no EDGAR signals.
  }
  registryCache = { at: Date.now(), byName };
  return byName;
}

/** Confident CIK for a company by exact normalized-name match. null if none. */
async function resolveCik(names: string[]): Promise<string | null> {
  const byName = await loadRegistry();
  if (byName.size === 0) return null;
  for (const n of names) {
    const key = normalizeName(n);
    if (!key) continue;
    const cik = byName.get(key);
    if (cik) return String(cik);
  }
  return null;
}

interface SubmissionsJson {
  filings?: {
    recent?: {
      accessionNumber?: string[];
      form?: string[];
      filingDate?: string[];
      items?: string[];
      primaryDocument?: string[];
    };
  };
}

interface Filing {
  accession: string;
  form: string;
  date: string;
  items: string;
  primaryDocument: string;
}

/** filings.recent is COLUMN-oriented (parallel arrays). Zip by index. */
function zipFilings(sub: SubmissionsJson): Filing[] {
  const r = sub.filings?.recent;
  if (!r?.accessionNumber) return [];
  const n = r.accessionNumber.length;
  const out: Filing[] = [];
  for (let i = 0; i < n; i++) {
    out.push({
      accession: r.accessionNumber[i] ?? "",
      form: r.form?.[i] ?? "",
      date: r.filingDate?.[i] ?? "",
      items: r.items?.[i] ?? "",
      primaryDocument: r.primaryDocument?.[i] ?? "",
    });
  }
  return out;
}

function withinLastYear(dateStr: string): boolean {
  if (!dateStr) return false;
  const d = new Date(dateStr).getTime();
  if (!Number.isFinite(d)) return false;
  return Date.now() - d <= 365 * 24 * 60 * 60 * 1000;
}

function evidenceFor(cik: string, f: Filing): Evidence {
  const acc = f.accession.replace(/-/g, "");
  return {
    title: `${f.form} filed ${f.date}`,
    url: `https://www.sec.gov/Archives/edgar/data/${cik}/${acc}/${f.primaryDocument}`,
    date: f.date,
  };
}

function emptySignal(name: CatalogId, detail: string): Signal {
  return { name, type: TYPE[name], found: false, detail, evidence: [] };
}

export async function scanEdgar(input: ScanInput): Promise<FunctionResult> {
  const company = (input.company || "").trim();
  try {
    if (!company) return { ok: false, signals: [], error: "company is required" };

    // Use the official resolved name for exact registrant matching.
    const entity = await resolveEntity(company, input.domain).catch(() => ({ name: company, industry: null }));
    const cik = await resolveCik([entity.name, company]);

    if (!cik) {
      const detail = "No SEC registrant matched. Company may be private or foreign-filed.";
      return {
        ok: true,
        signals: EDGAR_IDS.map((id) => emptySignal(id, detail)),
        meta: { cik: null, private: true, resolvedName: entity.name },
      };
    }

    const subRes = await secFetch(`https://data.sec.gov/submissions/CIK${padCik(cik)}.json`);
    if (!subRes.ok) return { ok: false, signals: [], error: `submissions HTTP ${subRes.status}` };
    const sub = (await subRes.json()) as SubmissionsJson;
    const filings = zipFilings(sub).filter((f) => withinLastYear(f.date));

    const is8k = (f: Filing, item: string) => f.form === "8-K" && f.items.includes(item);

    const buckets: Record<CatalogId, Filing[]> = {
      bankruptcy: filings.filter((f) => is8k(f, "1.03")),
      ma_activity: filings.filter((f) => is8k(f, "2.01") || ["DEFM14A", "SC 13D", "S-4"].includes(f.form)),
      leadership_change: filings.filter((f) => is8k(f, "5.02")),
      budget_cuts: filings.filter((f) => is8k(f, "2.05")),
      debt_restructuring: filings.filter((f) => is8k(f, "2.04")),
    } as Record<CatalogId, Filing[]>;

    const FOUND_DETAIL: Record<string, string> = {
      bankruptcy: "Chapter 11 / bankruptcy item 1.03 filed in the last year.",
      ma_activity: "Acquisition, merger or change-of-control filing in the last year.",
      leadership_change: "Officer or director change (8-K item 5.02) in the last year.",
      budget_cuts: "Restructuring / exit-and-disposal costs (8-K item 2.05) in the last year.",
      debt_restructuring: "Acceleration of a financial obligation (8-K item 2.04) in the last year.",
    };
    const EMPTY_DETAIL: Record<string, string> = {
      bankruptcy: "No bankruptcy filings in the last year.",
      ma_activity: "No acquisition or merger filings in the last year.",
      leadership_change: "No officer/director-change filings in the last year.",
      budget_cuts: "No restructuring-cost filings in the last year.",
      debt_restructuring: "No debt-acceleration filings in the last year.",
    };

    const signals: Signal[] = EDGAR_IDS.map((id) => {
      const hits = buckets[id];
      const found = hits.length > 0;
      return {
        name: id,
        type: TYPE[id],
        found,
        detail: found ? FOUND_DETAIL[id] : EMPTY_DETAIL[id],
        evidence: found ? hits.slice(0, 5).map((f) => evidenceFor(cik, f)) : [],
      };
    });

    return { ok: true, signals, meta: { cik, resolvedName: entity.name } };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}
