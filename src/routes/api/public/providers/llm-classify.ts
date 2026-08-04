/**
 * llm-classify.ts — accurate classification of already-fetched search results.
 *
 * Given a POOLED set of real search/Reddit results, Claude decides per signal
 * whether a result genuinely indicates that signal for the company AT THIS DOMAIN
 * and meets the ICP criteria — citing only the provided URLs (validated against
 * the sent set, so nothing is invented). Domain-guarded and ICP-strict. Never
 * throws; returns null so the caller can fall back to the deterministic gate.
 */

import type { CatalogId, Signal } from "../../../../lib/scan-contract";
import { CATALOG, isCatalogId } from "../../../../lib/scan-contract";
import {
  criteriaBlock,
  domainGuard,
  ICP_CRITERIA,
  productConstraint,
  sanitizeProducts,
} from "../../../../lib/icp";
import type { Hit } from "./search-provider";

const MODEL = process.env.SCAN_NEWS_MODEL || "claude-sonnet-4-6";
const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";

export function llmClassifyAvailable(): boolean {
  return !!process.env.ANTHROPIC_API_KEY;
}

interface RawSignal {
  name?: string;
  found?: unknown;
  detail?: unknown;
  evidence?: unknown;
  iaProducts?: unknown;
  soWhat?: unknown;
}

function buildSystem(
  company: string,
  domain: string,
  ids: CatalogId[],
  industry: string | null,
  description: string | null,
  today: string,
): string {
  return [
    `You classify retail B2B buying signals for Impact Analytics, an AI-native`,
    `retail decisioning platform. The target company is ${company}; its website is ${domain}${industry ? `; its industry is ${industry}` : ""}.`,
    description ? `About the target company: ${description}` : ``,
    `Today's date is ${today}.`,
    ``,
    domainGuard(company, domain, industry),
    ``,
    `You are given real web-search and Reddit results. For each signal id below, set`,
    `found:true ONLY when one of the PROVIDED results ALL of these hold:`,
    `  1. It is genuinely about ${company}, the company operating ${domain}${industry ? ` in ${industry}` : ""} —`,
    `     NOT a different company that merely shares the name, and NOT an article where`,
    `     "${company}" appears only as a common word or unrelated phrase. A result whose`,
    `     subject is a DIFFERENT legal entity, a differently-punctuated name, or a company`,
    `     in a different industry or country is NOT about the target, even if the words`,
    `     look similar. If the result does not clearly concern ${domain}, reject it.`,
    `  2. It is recent: dated within the last 365 days (on or after ${cutoffDate(today)}).`,
    `     If a result has no date or is clearly older than 365 days, do NOT use it.`,
    `  3. It satisfies the signal's criteria below.`,
    `If any of the three fails, that signal is found:false. When unsure, choose found:false.`,
    ``,
    `Signal criteria:`,
    criteriaBlock(ids),
    ``,
    `Rules:`,
    `- Use ONLY the provided results as evidence, cited by their EXACT url. NEVER invent`,
    `  a url or cite one not in the provided list.`,
    `- Every evidence item MUST include its date from the provided result. Prefer the most recent.`,
    `- detail: one sentence, max 100 characters, specific to the evidence.`,
    `- iaProducts: array of Impact Analytics products this opening fits (empty when found:false). ${productConstraint()}`,
    `- soWhat: one sentence, max 140 characters, why a rep cares and what to lead with (empty when found:false).`,
    `- Return ONLY a JSON array. No preamble, no markdown fences. One object per signal id`,
    `  below, all ${ids.length} present:`,
    `  { "name","found","detail","evidence":[{"title","url","date"}],"iaProducts":[],"soWhat" }`,
  ].join("\n");
}

function cutoffDate(todayIso: string): string {
  const t = Date.parse(todayIso);
  const base = Number.isNaN(t) ? Date.now() : t;
  return new Date(base - 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

function buildUser(hits: Hit[]): string {
  const lines = ["Candidate results (numbered):\n"];
  hits.slice(0, 60).forEach((h, i) => {
    lines.push(`[${i + 1}] ${h.title} — ${h.url}${h.date ? ` — ${h.date}` : ""}\n    ${h.snippet.slice(0, 220)}`);
  });
  lines.push("\nReturn the JSON array now.");
  return lines.join("\n");
}

function stripFences(t: string): string {
  return t.replace(/^\s*```(?:json)?/i, "").replace(/```\s*$/i, "").trim();
}
function extractJsonArray(t: string): string {
  const s = stripFences(t);
  const a = s.indexOf("["), b = s.lastIndexOf("]");
  return a === -1 || b === -1 || b < a ? s : s.slice(a, b + 1);
}

export async function classifyWithLLM(
  company: string,
  domain: string,
  hits: Hit[],
  ids: CatalogId[],
  opts: { industry?: string | null; description?: string | null } = {},
): Promise<Signal[] | null> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return null;
  const allowedUrls = new Set(hits.map((h) => h.url));
  const today = new Date().toISOString().slice(0, 10);
  const system = buildSystem(company, domain, ids, opts.industry ?? null, opts.description ?? null, today);
  const user = buildUser(hits);

  // Retry once on any failure so a transient error does NOT drop us to the
  // keyword fallback, which cannot tell a namesake apart from the target.
  for (let attempt = 0; attempt < 2; attempt++) {
    const result = await callOnce(apiKey, system, user, allowedUrls);
    if (result) return result;
  }
  return null;
}

async function callOnce(
  apiKey: string,
  system: string,
  user: string,
  allowedUrls: Set<string>,
): Promise<Signal[] | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 80_000);
  try {
    const res = await fetch(ANTHROPIC_URL, {
      method: "POST",
      signal: controller.signal,
      headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 4000,
        system,
        messages: [{ role: "user", content: user }],
      }),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
    const text = (data.content ?? [])
      .filter((b) => b.type === "text" && typeof b.text === "string")
      .map((b) => b.text as string)
      .join("\n");
    try {
      const arr = JSON.parse(extractJsonArray(text));
      if (!Array.isArray(arr)) return null;
      return coerce(arr as RawSignal[], allowedUrls);
    } catch {
      return null;
    }
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/** Reject evidence whose parseable date is older than 365 days. Undated kept. */
function isRecent(dateStr: string): boolean {
  if (!dateStr) return true;
  const t = Date.parse(dateStr);
  if (Number.isNaN(t)) return true;
  return t >= Date.now() - 365 * 24 * 60 * 60 * 1000;
}

function coerce(raw: RawSignal[], allowedUrls: Set<string>): Signal[] {
  const out: Signal[] = [];
  for (const item of raw) {
    const name = typeof item.name === "string" ? item.name.trim() : "";
    if (!isCatalogId(name)) continue;
    const found = item.found === true;
    const evidence = Array.isArray(item.evidence)
      ? item.evidence
          .filter((e): e is { title?: string; url?: string; date?: string } => !!e && typeof e === "object")
          .filter((e) => typeof e.url === "string" && allowedUrls.has(e.url))
          .filter((e) => isRecent(String(e.date ?? "")))
          .slice(0, 5)
          .map((e) => ({ title: String(e.title ?? "").slice(0, 200), url: String(e.url), date: String(e.date ?? "") }))
      : [];
    const reallyFound = found && evidence.length > 0;
    out.push({
      name,
      type: CATALOG[name].type,
      found: reallyFound,
      detail: reallyFound
        ? (typeof item.detail === "string" && item.detail.trim() ? item.detail.trim().slice(0, 100) : ICP_CRITERIA[name].title)
        : "No confirmed signals found",
      evidence: reallyFound ? evidence : [],
      iaProducts: reallyFound ? sanitizeProducts(item.iaProducts) : [],
      soWhat: reallyFound && typeof item.soWhat === "string" ? item.soWhat.slice(0, 140) : "",
    });
  }
  return out;
}
