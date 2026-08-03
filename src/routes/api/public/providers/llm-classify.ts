/**
 * llm-classify.ts — accurate classification of *already-fetched* search results.
 *
 * The deterministic keyword classifier (classify.ts) is fast and keyless but
 * coarse: it fires whenever a result mentions the company name token, which
 * misfires on similarly-named companies (fila.com → F.I.L.A.) and can't judge
 * ICP-relevance. When an Anthropic key is present, this module hands the REAL
 * SerpAPI results to Claude and asks it to decide, per signal, whether a result
 * genuinely indicates that signal for the company AT THIS DOMAIN and meets the
 * ICP criteria — citing only the provided URLs, never inventing one.
 *
 * Grounded (evidence is validated against the provided URL set), domain-guarded,
 * and ICP-strict. Never throws; returns null so the caller can fall back to the
 * deterministic classifier.
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

export interface SignalCandidates {
  id: CatalogId;
  hits: Hit[];
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
    `retail decisioning platform. The target company is ${company}; its website is`,
    `${domain}.`,
    ``,
    domainGuard(company, domain),
    ``,
    `You are given real web-search results. For each signal id below, set found:true`,
    `ONLY when one of the PROVIDED results genuinely indicates that signal for THIS`,
    `company (the one at ${domain}) AND satisfies the signal's criteria. Judge`,
    `strictly: a result about a similarly-named but different company, or one that`,
    `does not meet the criteria, is found:false.`,
    ``,
    `Signal criteria:`,
    criteriaBlock(ids),
    ``,
    `Rules:`,
    `- Use ONLY the provided results as evidence, and cite them by their EXACT url.`,
    `  NEVER invent a url or cite one not in the provided list.`,
    `- detail: one sentence, max 100 characters, specific to what the evidence shows.`,
    `- iaProducts: array of Impact Analytics products this opening fits (empty when`,
    `  found:false). ${productConstraint()}`,
    `- soWhat: one sentence, max 140 characters, on why a rep should care and what to`,
    `  lead with (empty string when found:false).`,
    `- Return ONLY a JSON array. No preamble, no markdown fences. One object per`,
    `  signal id below, all ${ids.length} present, even when found is false:`,
    `  { "name": string, "found": boolean, "detail": string,`,
    `    "evidence": [ { "title": string, "url": string, "date": string } ],`,
    `    "iaProducts": string[], "soWhat": string }`,
  ].join("\n");
}

function buildUser(groups: SignalCandidates[]): string {
  const blocks: string[] = ["Candidate search results:\n"];
  for (const g of groups) {
    blocks.push(`## ${g.id}`);
    if (g.hits.length === 0) {
      blocks.push("(no results returned for this signal)");
    } else {
      g.hits.slice(0, 6).forEach((h, i) => {
        blocks.push(
          `[${i + 1}] ${h.title} — ${h.url}${h.date ? ` — ${h.date}` : ""}\n    ${h.snippet.slice(0, 240)}`,
        );
      });
    }
    blocks.push("");
  }
  blocks.push("Return the JSON array now.");
  return blocks.join("\n");
}

function stripFences(text: string): string {
  return text.replace(/^\s*```(?:json)?/i, "").replace(/```\s*$/i, "").trim();
}

function extractJsonArray(text: string): string {
  const s = stripFences(text);
  const start = s.indexOf("[");
  const end = s.lastIndexOf("]");
  if (start === -1 || end === -1 || end < start) return s;
  return s.slice(start, end + 1);
}

export async function classifyWithLLM(
  company: string,
  domain: string,
  groups: SignalCandidates[],
): Promise<Signal[] | null> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return null;

  // The exact set of real URLs we sent — used to reject any invented evidence.
  const allowedUrls = new Set<string>();
  for (const g of groups) for (const h of g.hits) allowedUrls.add(h.url);

  const ids = groups.map((g) => g.id);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 80_000);
  try {
    const res = await fetch(ANTHROPIC_URL, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 4000,
        system: buildSystem(company, domain, ids),
        messages: [{ role: "user", content: buildUser(groups) }],
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
    // Evidence must reference URLs we actually provided — this is the anti-invention guard.
    const evidence = Array.isArray(item.evidence)
      ? item.evidence
          .filter((e): e is { title?: string; url?: string; date?: string } => !!e && typeof e === "object")
          .filter((e) => typeof e.url === "string" && allowedUrls.has(e.url))
          .slice(0, 5)
          .map((e) => ({
            title: String(e.title ?? "").slice(0, 200),
            url: String(e.url),
            date: String(e.date ?? ""),
          }))
      : [];
    // Found requires at least one grounded (provided) URL — no evidence, no signal.
    const reallyFound = found && evidence.length > 0;
    out.push({
      name,
      type: CATALOG[name].type,
      found: reallyFound,
      detail: reallyFound
        ? (typeof item.detail === "string" && item.detail.trim()
            ? item.detail.trim().slice(0, 100)
            : ICP_CRITERIA[name].title)
        : "No confirmed signals found",
      evidence: reallyFound ? evidence : [],
      iaProducts: reallyFound ? sanitizeProducts(item.iaProducts) : [],
      soWhat: reallyFound && typeof item.soWhat === "string" ? item.soWhat.slice(0, 140) : "",
    });
  }
  return out;
}
