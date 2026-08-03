/**
 * jobs-provider.ts — a dedicated jobs feed for hiring signals. Two backends:
 *   - SerpAPI Google Jobs   (SERPAPI_KEY)
 *   - Adzuna                (ADZUNA_APP_ID + ADZUNA_APP_KEY)
 *
 * Produces two catalog signals:
 *   hiring_activity  — relevant planning/merchandising/analytics roles are open
 *   no_job_openings  — an active search found no relevant roles
 * Never throws.
 */

import type { Signal } from "../../../../lib/scan-contract";
import { ICP_CRITERIA } from "../../../../lib/icp";

// Only these roles count — the ICP-relevant hiring criteria.
const RELEVANT_ROLES = [
  "demand planner", "merchandise planner", "allocation analyst", "replenishment",
  "inventory analyst", "inventory manager", "pricing analyst", "pricing manager",
  "markdown", "promotions analyst", "category manager", "space planner",
  "assortment planner", "buyer planner", "retail data scientist", "analytics engineer",
  "data engineer",
];

// Competitor tools worth capturing from a JD — reveals the incumbent stack.
const COMPETITOR_TOOLS = [
  "RELEX", "o9", "Blue Yonder", "JDA", "Oracle Retail", "SAP", "Aptos",
  "Anaplan", "Logility", "Manhattan", "ToolsGroup", "Kinaxis", "Increff",
];

interface Posting {
  title: string;
  url: string;
  date: string;
  description: string;
}

interface JobsBackend {
  name: string;
  search: (company: string, query: string) => Promise<Posting[]>;
}

async function fetchJson(url: string, timeoutMs = 12_000): Promise<unknown | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function serpJobs(key: string): JobsBackend {
  const base = process.env.SERPAPI_BASE_URL || "https://serpapi.com";
  return {
    name: "serpapi_jobs",
    async search(company, query) {
      const url =
        `${base}/search.json?engine=google_jobs` +
        `&q=${encodeURIComponent(`${company} ${query}`)}&api_key=${encodeURIComponent(key)}`;
      const data = (await fetchJson(url)) as { jobs_results?: Array<Record<string, unknown>> } | null;
      return (data?.jobs_results ?? []).map((j) => ({
        title: String(j.title ?? ""),
        url: String((j as { share_link?: string }).share_link ?? ""),
        date: String((j.detected_extensions as { posted_at?: string } | undefined)?.posted_at ?? ""),
        description: String(j.description ?? ""),
      }));
    },
  };
}

function adzuna(appId: string, appKey: string): JobsBackend {
  return {
    name: "adzuna",
    async search(company, query) {
      const url =
        `https://api.adzuna.com/v1/api/jobs/us/search/1?app_id=${encodeURIComponent(appId)}` +
        `&app_key=${encodeURIComponent(appKey)}&what=${encodeURIComponent(query)}` +
        `&company=${encodeURIComponent(company)}&results_per_page=20`;
      const data = (await fetchJson(url)) as { results?: Array<Record<string, unknown>> } | null;
      return (data?.results ?? []).map((j) => ({
        title: String(j.title ?? ""),
        url: String(j.redirect_url ?? ""),
        date: String(j.created ?? ""),
        description: String(j.description ?? ""),
      }));
    },
  };
}

function getBackend(): JobsBackend | null {
  if (process.env.SERPAPI_KEY) return serpJobs(process.env.SERPAPI_KEY);
  if (process.env.ADZUNA_APP_ID && process.env.ADZUNA_APP_KEY) {
    return adzuna(process.env.ADZUNA_APP_ID, process.env.ADZUNA_APP_KEY);
  }
  return null;
}

function isRelevant(p: Posting): boolean {
  const t = `${p.title} ${p.description}`.toLowerCase();
  return RELEVANT_ROLES.some((r) => t.includes(r));
}

export interface JobsResult {
  available: boolean;
  signals: Signal[];
  error?: string;
}

export async function scanJobs(company: string, _domain: string): Promise<JobsResult> {
  const backend = getBackend();
  if (!backend) {
    return { available: false, signals: [], error: "No jobs API key configured." };
  }
  try {
    const postings = await backend.search(company, "planner OR allocation OR pricing OR merchandising analyst");
    const relevant = postings.filter(isRelevant);

    // Capture any competitor tool named in a relevant JD.
    const toolsSeen = new Set<string>();
    for (const p of relevant) {
      const text = `${p.title} ${p.description}`;
      for (const tool of COMPETITOR_TOOLS) {
        if (new RegExp(`\\b${tool}\\b`, "i").test(text)) toolsSeen.add(tool);
      }
    }

    const hiringCriteria = ICP_CRITERIA.hiring_activity;
    const cluster = relevant.length >= 3;
    const toolNote = toolsSeen.size ? ` Incumbent tools named: ${[...toolsSeen].join(", ")}.` : "";

    const hiring: Signal = {
      name: "hiring_activity",
      type: "positive",
      found: relevant.length > 0,
      detail:
        relevant.length > 0
          ? `${relevant.length} relevant planning role${relevant.length > 1 ? "s" : ""} open${cluster ? " (a hiring cluster)" : ""}.${toolNote}`.slice(0, 100)
          : "No confirmed signals found",
      evidence: relevant.slice(0, 5).map((p) => ({ title: p.title.slice(0, 200), url: p.url, date: p.date })),
      iaProducts: relevant.length > 0 ? hiringCriteria.iaProducts.slice(0, 5) : [],
      soWhat: relevant.length > 0 ? hiringCriteria.soWhatHint.slice(0, 140) : "",
    };

    // no_job_openings is a real negative only when we searched and found nothing.
    const noJobs: Signal = {
      name: "no_job_openings",
      type: "negative",
      found: postings.length >= 0 && relevant.length === 0,
      detail:
        relevant.length === 0
          ? "Searched jobs feed and found no relevant planning roles."
          : "No confirmed signals found",
      evidence: [],
      iaProducts: [],
      soWhat: relevant.length === 0 ? ICP_CRITERIA.no_job_openings.soWhatHint.slice(0, 140) : "",
    };

    return { available: true, signals: [hiring, noJobs] };
  } catch (err) {
    return { available: false, signals: [], error: (err as Error).message };
  }
}
