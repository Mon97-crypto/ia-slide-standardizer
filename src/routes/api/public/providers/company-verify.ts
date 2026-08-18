/**
 * company-verify.ts — authoritative, CURRENT company facts for the Account card.
 *
 * Apollo's free-text description is often stale (e.g. it calls Fila "Italian" when
 * Fila is today a South Korean brand owned by Fila Holdings Corp). For crucial,
 * user-facing facts we verify against live web sources via Claude web search, keyed
 * to the exact domain, and return a corrected description + headquarters. Grounded:
 * the model must use web search and report only what it can verify. Never throws.
 */

const MODEL = process.env.SCAN_NEWS_MODEL || "claude-sonnet-4-6";
const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";

export function companyVerifyAvailable(): boolean {
  return !!process.env.ANTHROPIC_API_KEY;
}

export interface VerifiedCompany {
  description: string | null;
  headquarters: string | null;
  founded: string | null;
  ownership: string | null;
  sources: string[];
}

interface Raw {
  description?: unknown;
  headquarters?: unknown;
  founded?: unknown;
  ownership?: unknown;
}

function str(v: unknown, max: number): string | null {
  return typeof v === "string" && v.trim() ? v.trim().slice(0, max) : null;
}

function extractJsonObject(text: string): string {
  const s = text.replace(/^\s*```(?:json)?/i, "").replace(/```\s*$/i, "").trim();
  const a = s.indexOf("{");
  const b = s.lastIndexOf("}");
  return a === -1 || b === -1 || b < a ? s : s.slice(a, b + 1);
}

export async function verifyCompany(
  name: string,
  domain: string,
): Promise<VerifiedCompany | null> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey || !domain) return null;

  const system = [
    `You produce ACCURATE, CURRENT facts about the company that operates the website ${domain}`,
    `(commonly known as ${name}). Use web search to verify. Accuracy is critical — this is`,
    `shown to a sales team and must not be wrong or outdated.`,
    ``,
    `Rules:`,
    `- Confirm you are describing the company at ${domain}, not a similarly-named different company.`,
    `- Report the CURRENT state, not historical. If ownership/nationality changed, state today's`,
    `  reality first (e.g. current parent company and country), and note founding origin only as history.`,
    `- headquarters: the primary/global headquarters as "City, Country".`,
    `- founded: the founding year as a string, or "" if unknown.`,
    `- ownership: current parent company, or "Public (TICKER)", or "Private", or "" if unknown.`,
    `- description: two sentences, factual and current, covering what the company is, what it sells,`,
    `  and its current ownership/country. No marketing language.`,
    `- Only state facts you verified via search. If you cannot verify a field, use "" for it.`,
    `- Return ONLY a JSON object, no prose, no markdown fences:`,
    `  { "description": string, "headquarters": string, "founded": string, "ownership": string }`,
  ].join("\n");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45_000);
  try {
    const res = await fetch(ANTHROPIC_URL, {
      method: "POST",
      signal: controller.signal,
      headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 1024,
        system,
        tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 4 }],
        messages: [{ role: "user", content: `Verify and return the JSON for ${name} (${domain}).` }],
      }),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
    const blocks = data.content ?? [];
    const text = blocks
      .filter((b) => b.type === "text" && typeof b.text === "string")
      .map((b) => b.text as string)
      .join("\n");
    // Collect any web-search result URLs the model was given, as sources.
    const sources: string[] = [];
    for (const b of blocks as Array<Record<string, unknown>>) {
      if (b.type === "web_search_tool_result" && Array.isArray(b.content)) {
        for (const r of b.content as Array<Record<string, unknown>>) {
          if (typeof r.url === "string") sources.push(r.url);
        }
      }
    }
    let raw: Raw;
    try {
      raw = JSON.parse(extractJsonObject(text)) as Raw;
    } catch {
      return null;
    }
    return {
      description: str(raw.description, 320),
      headquarters: str(raw.headquarters, 80),
      founded: str(raw.founded, 12),
      ownership: str(raw.ownership, 120),
      sources: sources.slice(0, 5),
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
