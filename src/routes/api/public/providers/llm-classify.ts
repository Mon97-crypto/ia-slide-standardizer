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

function buildSystem(company: string, domain: string, ids: CatalogId[]): string {
  return [
    `You classify retail B2B buying signals for Impact Analytics, an AI-native`,
    `retail decisioning platform. The target company is ${company}; its website is ${domain}.`,
    ``,
    domainGuard(company, domain),
    ``,
    `You are given real web-search and Reddit results. For each signal id below, set`,
    `found:true ONLY when one of the PROVIDED results genuinely indicates that signal`,
    `for THIS company (at ${domain}) AND satisfies the signal's criteria. Judge`,
    `strictly: a result about a similarly-named but different company, or one that does`,
    `not meet the criteria, is found:false.`,
    ``,
    `Signal criteria:`,
    criteriaBlock(ids),
    ``,
    `Rules:`,
    `- Use ONLY the provided results as evidence, cited by their EXACT url. NEVER invent`,
    `  a url or cite one not in the provided list.`,
    `- detail: one sentence, max 100 characters, specific to the evidence.`,
    `- iaProducts: array of Impact Analytics products this opening fits (empty when found:false). ${productConstraint()}`,
    `- soWhat: one sentence, max 140 characters, why a rep cares and what to lead with (empty when found:false).`,
    `- Return ONLY a JSON array. No preamble, no markdown fences. One object per signal id`,
    `  below, all ${ids.length} present:`,
    `  { "name","found","detail","evidence":[{"title","url","date"}],"iaProducts":[],"soWhat" }`,
  ].join("\n");
}

function buildUser(hits: Hit[]): string {
  const lines = ["Candidate results (numbered):\n"];
  hits.slice(0, 40).forEach((h, i) => {
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
): Promise<Signal[] | null> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return null;
  const allowedUrls = new Set(hits.map((h) => h.url));

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
        system: buildSystem(company, domain, ids),
        messages: [{ role: "user", content: buildUser(hits) }],
      }),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
    const text = (data.content ?? [])
      .filter((b) => b.type === "text" && typeof b.text === "string")
      .map((b) => b.text as string)
      .join("\n");
    let raw: RawSignal[];
    try {
      const arr = JSON.parse(extractJsonArray(text));
      if (!Array.isArray(arr)) return null;
      raw = arr as RawSignal[];
    } catch {
      return null;
    }
    return coerce(raw, allowedUrls);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
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
