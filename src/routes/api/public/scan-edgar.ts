/**
 * scan-edgar.ts — SEC EDGAR signals. No API key required; the SEC APIs are free
 * and public. Accepts POST { company, domain } and returns the contract shape.
 *
 * Signals derived (last 365 days of filings):
 *   bankruptcy      : 8-K with item 1.03
 *   reorganization  : 8-K with item 2.05
 *   ma_activity     : 8-K item 2.01, or DEFM14A / SC 13D / S-4
 *   ipo_preparation : form starting with S-1
 */

import type { Evidence, FunctionResult, Signal } from "../../../lib/scan-contract";
import { padCik, secFetch } from "./_sec";

interface ScanInput {
  company: string;
  domain: string;
}

const TODAY = () => new Date().toISOString().slice(0, 10);

interface FtsHit {
  _source?: { ciks?: string[] };
}

async function resolveCik(company: string): Promise<string | null> {
  const q = encodeURIComponent(`"${company}"`);
  const base = "https://efts.sec.gov/LATEST/search-index";
  const urls = [
    `${base}?q=${q}&forms=10-K,8-K&startdt=2015-01-01&enddt=${TODAY()}`,
    `${base}?q=${q}&startdt=2010-01-01&enddt=${TODAY()}`,
  ];
  for (const url of urls) {
    try {
      const res = await secFetch(url);
      if (!res.ok) continue;
      const data = (await res.json()) as { hits?: { hits?: FtsHit[] } };
      const hits = data.hits?.hits ?? [];
      const ciks = hits
        .flatMap((h) => h._source?.ciks ?? [])
        .map((c) => parseInt(String(c), 10))
        .filter((n) => Number.isFinite(n));
      if (ciks.length) return String(Math.min(...ciks));
    } catch {
      // try the next url
    }
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

function emptySignal(name: string, type: Signal["type"], detail: string): Signal {
  return { name, type, found: false, detail, evidence: [] };
}

export async function scanEdgar(input: ScanInput): Promise<FunctionResult> {
  const company = (input.company || "").trim();
  try {
    if (!company) {
      return { ok: false, signals: [], error: "company is required" };
    }

    const cik = await resolveCik(company);
    if (!cik) {
      const detail = "No SEC filings found. Company may be private.";
      return {
        ok: true,
        signals: [
          emptySignal("bankruptcy", "negative", detail),
          emptySignal("reorganization", "neutral", detail),
          emptySignal("ma_activity", "positive", detail),
          emptySignal("ipo_preparation", "positive", detail),
        ],
        meta: { cik: null, private: true },
      };
    }

    const subRes = await secFetch(
      `https://data.sec.gov/submissions/CIK${padCik(cik)}.json`,
    );
    if (!subRes.ok) {
      return { ok: false, signals: [], error: `submissions HTTP ${subRes.status}` };
    }
    const sub = (await subRes.json()) as SubmissionsJson;
    const filings = zipFilings(sub).filter((f) => withinLastYear(f.date));

    const bankruptcyHits = filings.filter(
      (f) => f.form === "8-K" && f.items.includes("1.03"),
    );
    const reorgHits = filings.filter(
      (f) => f.form === "8-K" && f.items.includes("2.05"),
    );
    const maHits = filings.filter(
      (f) =>
        (f.form === "8-K" && f.items.includes("2.01")) ||
        ["DEFM14A", "SC 13D", "S-4"].includes(f.form),
    );
    const ipoHits = filings.filter((f) => f.form.startsWith("S-1"));

    const signals: Signal[] = [
      buildSignal("bankruptcy", "negative", bankruptcyHits, cik,
        "Chapter 11 or bankruptcy item 1.03 filed in the last year.",
        "No bankruptcy filings in the last year."),
      buildSignal("reorganization", "neutral", reorgHits, cik,
        "Restructuring item 2.05 filed in the last year.",
        "No restructuring filings in the last year."),
      buildSignal("ma_activity", "positive", maHits, cik,
        "Acquisition or merger filing in the last year.",
        "No acquisition or merger filings in the last year."),
      buildSignal("ipo_preparation", "positive", ipoHits, cik,
        "S-1 registration filed in the last year.",
        "No S-1 registration in the last year."),
    ];

    return { ok: true, signals, meta: { cik } };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}

function buildSignal(
  name: string,
  type: Signal["type"],
  hits: Filing[],
  cik: string,
  foundDetail: string,
  emptyDetail: string,
): Signal {
  const found = hits.length > 0;
  return {
    name,
    type,
    found,
    detail: found ? foundDetail : emptyDetail,
    evidence: hits.slice(0, 5).map((f) => evidenceFor(cik, f)),
  };
}
