/**
 * jobs-provider.ts — a dedicated jobs feed for the hiring_activity signal. Backends:
 *   - SerpAPI Google Jobs   (SERPAPI_KEY)
 *   - Adzuna                (ADZUNA_APP_ID + ADZUNA_APP_KEY)
 *
 * ICP accuracy: postings are first restricted to the TARGET company, then judged
 * against the hiring_activity ICP criteria. When ANTHROPIC_API_KEY is set the LLM
 * classifier makes the call (qualify roles only; reject store/warehouse/marketing/
 * HR/sales), so the signal follows the ICP without fail. Otherwise a strict
 * must/reject keyword gate is used. Never throws.
 */

import type { Signal } from "../../../../lib/scan-contract";
import { ICP_CRITERIA } from "../../../../lib/icp";
import type { Hit } from "./search-provider";
import { classifyWithLLM, llmClassifyAvailable } from "./llm-classify";
import { resolveEntity } from "../account-info";

// ICP-relevant roles (planning / merchandising / supply-chain / retail analytics).
const RELEVANT_ROLES = [
  "demand planner", "demand planning", "merchandise planner", "merchandise planning",
  "allocation", "replenishment", "inventory planner", "inventory analyst", "inventory manager",
  "pricing analyst", "pricing manager", "markdown", "promotions analyst", "promotion planner",
  "category manager", "category management", "space planner", "space planning",
  "assortment planner", "assortment planning", "buyer planner", "buying and planning",
  "merchandise financial planner", "merchandising analyst", "retail data scientist",
  "supply chain analyst", "supply chain planner", "forecasting analyst", "demand forecasting",
];

// Never ICP hiring, even if a relevant word appears somewhere in the text.
const REJECT_ROLES = [
  "store associate", "sales associate", "retail associate", "cashier", "stock associate",
  "warehouse", "picker", "packer", "stocker", "fulfillment associate", "driver", "delivery",
  "security", "loss prevention", "janitor", "custodian", "housekeeping", "barista", "cook",
  "server", "host", "greeter", "recruiter", "human resources", "talent acquisition",
  "marketing", "brand ambassador", "social media", "public relations", "communications",
  "legal", "counsel", "facilities", "maintenance", "software engineer", "customer service",
];

const COMPETITOR_TOOLS = [
  "RELEX", "o9", "Blue Yonder", "JDA", "Oracle Retail", "SAP", "Aptos",
  "Anaplan", "Logility", "Manhattan", "ToolsGroup", "Kinaxis", "Increff",
];

interface Posting {
  title: string;
  url: string;
  date: string;
  description: string;
  company: string;
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
        company: String(j.company_name ?? ""),
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
        company: String((j.company as { display_name?: string } | undefined)?.display_name ?? ""),
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

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** Keep only postings that are actually AT the target company. */
function atTargetCompany(p: Posting, company: string, domain: string): boolean {
  if (!p.company) return false;
  const pc = norm(p.company);
  const t = norm(company);
  const slug = norm(domain.split(".")[0] || "");
  return (t.length >= 3 && (pc.includes(t) || t.includes(pc))) || (slug.length >= 3 && pc.includes(slug));
}

function isIcpRole(p: Posting): boolean {
  const t = `${p.title} ${p.description}`.toLowerCase();
  if (REJECT_ROLES.some((r) => t.includes(r))) return false;
  return RELEVANT_ROLES.some((r) => t.includes(r));
}

export interface JobsResult {
  available: boolean;
  signals: Signal[];
  error?: string;
}

function emptyHiring(): Signal {
  return { name: "hiring_activity", type: "positive", found: false, detail: "No confirmed signals found", evidence: [], iaProducts: [], soWhat: "" };
}

export async function scanJobs(company: string, domain: string): Promise<JobsResult> {
  const backend = getBackend();
  if (!backend) return { available: false, signals: [], error: "No jobs API key configured." };
  try {
    const postings = await backend.search(
      company,
      "planner OR allocation OR replenishment OR merchandising OR pricing OR inventory OR forecasting OR assortment analyst",
    );
    // Restrict to the target company. If no posting carries a company name, keep all
    // and rely on the ICP gate below rather than dropping everything.
    const named = postings.filter((p) => p.company);
    const scoped = named.length ? named.filter((p) => atTargetCompany(p, company, domain)) : postings;

    if (scoped.length === 0) return { available: true, signals: [emptyHiring()] };

    // Preferred path: let the LLM apply the full hiring ICP criteria (qualify roles,
    // reject store/warehouse/marketing/HR/sales) against postings at this company.
    if (llmClassifyAvailable()) {
      const entity = await resolveEntity(company, domain).catch(() => ({ name: company, industry: null, description: null }));
      const hits: Hit[] = scoped.slice(0, 25).map((p) => ({
        title: p.title,
        url: p.url,
        date: p.date,
        snippet: `Employer: ${p.company || company}. ${p.description}`.slice(0, 320),
      }));
      const signals = await classifyWithLLM(entity.name, domain, hits, ["hiring_activity"], {
        industry: entity.industry,
        description: entity.description,
      });
      if (signals && signals.length) return { available: true, signals };
    }

    // Deterministic fallback: strict must/reject role gate on company-scoped postings.
    const relevant = scoped.filter(isIcpRole);
    if (relevant.length === 0) return { available: true, signals: [emptyHiring()] };

    const toolsSeen = new Set<string>();
    for (const p of relevant) {
      const text = `${p.title} ${p.description}`;
      for (const tool of COMPETITOR_TOOLS) {
        if (new RegExp(`\\b${tool}\\b`, "i").test(text)) toolsSeen.add(tool);
      }
    }
    const crit = ICP_CRITERIA.hiring_activity;
    const cluster = relevant.length >= 3;
    const toolNote = toolsSeen.size ? ` Incumbent tools named: ${[...toolsSeen].join(", ")}.` : "";
    const hiring: Signal = {
      name: "hiring_activity",
      type: "positive",
      found: true,
      detail: `${relevant.length} ICP planning role${relevant.length > 1 ? "s" : ""} open at ${company}${cluster ? " (a hiring cluster)" : ""}.${toolNote}`.slice(0, 100),
      evidence: relevant.slice(0, 5).map((p) => ({ title: p.title.slice(0, 200), url: p.url, date: p.date })),
      iaProducts: crit.iaProducts.slice(0, 5),
      soWhat: crit.soWhatHint.slice(0, 140),
    };
    return { available: true, signals: [hiring] };
  } catch (err) {
    return { available: false, signals: [], error: (err as Error).message };
  }
}
