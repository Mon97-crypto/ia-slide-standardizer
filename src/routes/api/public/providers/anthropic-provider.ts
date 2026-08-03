/**
 * scan-news.ts — AI-researched signals. Calls the Anthropic API DIRECTLY with
 * fetch (NOT through any billed connector), with the web search tool enabled, and
 * asks the model to assess the 11 news-sourced catalog signals over the last 12
 * months against Impact Analytics' ICP criteria.
 *
 * The API key is read from ANTHROPIC_API_KEY (server-side secret only — never in
 * src that ships to the browser; this file is imported only by the Node server).
 *
 * Contract: never throws. On any failure returns ok:false with an EMPTY signals
 * array so a partial scan still renders.
 */

import type { CatalogId, FunctionResult, Signal } from "../../../../lib/scan-contract";
import { CATALOG, isCatalogId } from "../../../../lib/scan-contract";
import {
  criteriaBlock,
  domainGuard,
  ICP_CRITERIA,
  productConstraint,
  sanitizeProducts,
  SEARCH_SIGNAL_IDS,
} from "../../../../lib/icp";

interface ScanInput {
  company: string;
  domain: string;
}

// The signals the AI fallback covers: every search-derived signal + hiring.
const NEWS_SIGNALS: CatalogId[] = [...SEARCH_SIGNAL_IDS, "hiring_activity"];

const MODEL = process.env.SCAN_NEWS_MODEL || "claude-sonnet-4-6";
const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";

function buildSystemPrompt(company: string, domain: string): string {
  return [
    `You research B2B sales signals for Impact Analytics, an AI-native retail`,
    `decisioning platform. Assess ${company} (${domain}) over the LAST 12 MONTHS`,
    `for exactly these ${NEWS_SIGNALS.length} signals, judged against Impact`,
    `Analytics' ideal-customer criteria.`,
    ``,
    domainGuard(company, domain),
    ``,
    `Qualifying criteria per signal (only fire a signal when its criteria are met):`,
    criteriaBlock(NEWS_SIGNALS),
    ``,
    `Rules:`,
    `- Return ONLY a JSON array. No preamble, no markdown fences, no commentary.`,
    `- One object per signal id above, all ${NEWS_SIGNALS.length} present, even when found is false.`,
    `- Set found:true ONLY with a specific dated source about THIS company. Absence of`,
    `  evidence is found:false with detail "No confirmed signals found" — never speculate,`,
    `  never infer from industry trends.`,
    `- Every evidence item needs a real url returned by web search. Never construct or guess`,
    `  a URL. If you have no url, drop the evidence item.`,
    `- Exclude articles about FORMER employees or alumni when judging leadership_change.`,
    `- operational_pain requires a confirmed inventory or price failure, not vague "challenges".`,
    `- erp_crm_migration requires an active change verb (implementing, migrating, deploying,`,
    `  replacing, rolling out), not a partnership or integration announcement.`,
    `- no_job_openings is found:true only when you actively searched and found no current`,
    `  postings. Never true by default.`,
    `- detail is one sentence, max 100 characters.`,
    `- Add "iaProducts": an array of Impact Analytics product names this signal creates an`,
    `  opening for (empty when found is false). ${productConstraint()}`,
    `- Add "soWhat": one sentence, max 140 chars, on why a rep should care and what to lead`,
    `  with (empty string when found is false).`,
    ``,
    `Each object: { "name": string, "found": boolean, "detail": string,`,
    `  "evidence": [ { "title": string, "url": string, "date": string } ],`,
    `  "iaProducts": string[], "soWhat": string }`,
  ].join("\n");
}

interface RawSignal {
  name?: string;
  found?: unknown;
  detail?: unknown;
  evidence?: unknown;
  iaProducts?: unknown;
  soWhat?: unknown;
}

function stripFences(text: string): string {
  return text
    .replace(/^\s*```(?:json)?/i, "")
    .replace(/```\s*$/i, "")
    .trim();
}

/** Pull the first JSON array out of the model's text, tolerating stray prose. */
function extractJsonArray(text: string): string {
  const stripped = stripFences(text);
  const start = stripped.indexOf("[");
  const end = stripped.lastIndexOf("]");
  if (start === -1 || end === -1 || end < start) return stripped;
  return stripped.slice(start, end + 1);
}

function coerceSignals(raw: RawSignal[]): Signal[] {
  const out: Signal[] = [];
  for (const item of raw) {
    const name = typeof item.name === "string" ? item.name.trim() : "";
    if (!isCatalogId(name)) continue; // drop anything not in the catalog
    const evidence = Array.isArray(item.evidence)
      ? item.evidence
          .filter(
            (e): e is { title?: string; url?: string; date?: string } =>
              !!e && typeof e === "object",
          )
          .filter((e) => typeof e.url === "string" && e.url.trim().length > 0)
          .slice(0, 5)
          .map((e) => ({
            title: String(e.title ?? "").slice(0, 200),
            url: String(e.url),
            date: String(e.date ?? ""),
          }))
      : [];
    const found = item.found === true;
    out.push({
      name,
      type: CATALOG[name].type, // type comes from the catalog, not the model
      found,
      detail:
        typeof item.detail === "string" && item.detail.trim()
          ? item.detail.trim().slice(0, 100)
          : found
            ? ICP_CRITERIA[name].title
            : "No confirmed signals found",
      evidence,
      iaProducts: found ? sanitizeProducts(item.iaProducts) : [],
      soWhat:
        found && typeof item.soWhat === "string" ? item.soWhat.slice(0, 140) : "",
    });
  }
  return out;
}

export function anthropicAvailable(): boolean {
  return !!process.env.ANTHROPIC_API_KEY;
}

export async function scanNewsAnthropic(input: ScanInput): Promise<FunctionResult> {
  const { company, domain } = input;
  const apiKey = process.env.ANTHROPIC_API_KEY;
  try {
    if (!apiKey) {
      return {
        ok: false,
        signals: [],
        error: "ANTHROPIC_API_KEY is not configured on the server.",
      };
    }
    if (!company) return { ok: false, signals: [], error: "company is required" };

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 85_000);
    let res: Response;
    try {
      res = await fetch(ANTHROPIC_URL, {
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
          system: buildSystemPrompt(company, domain),
          tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 8 }],
          messages: [
            {
              role: "user",
              content: `Research ${company} (${domain}) and return the JSON array now.`,
            },
          ],
        }),
      });
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return { ok: false, signals: [], error: `Anthropic HTTP ${res.status}: ${body.slice(0, 200)}` };
    }

    const data = (await res.json()) as {
      content?: Array<{ type: string; text?: string }>;
    };
    const text = (data.content ?? [])
      .filter((b) => b.type === "text" && typeof b.text === "string")
      .map((b) => b.text as string)
      .join("\n");

    let parsed: RawSignal[];
    try {
      const arr = JSON.parse(extractJsonArray(text));
      if (!Array.isArray(arr)) throw new Error("not an array");
      parsed = arr as RawSignal[];
    } catch {
      return { ok: false, signals: [], error: "Could not parse model output as JSON." };
    }

    return { ok: true, signals: coerceSignals(parsed), meta: { model: MODEL } };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}
