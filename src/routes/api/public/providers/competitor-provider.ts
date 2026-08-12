/**
 * competitor-provider.ts — "Competitor footprint". Uses Claude web search to find
 * VERIFIABLE public evidence that a target retailer uses, is implementing, is
 * evaluating, or recently selected a competitor of Impact Analytics. Accuracy is
 * the priority: every finding must cite a real dated URL that names BOTH the
 * target and the competitor in a real relationship — no inference, no padding.
 * Never throws.
 */

const MODEL = process.env.SCAN_NEWS_MODEL || "claude-sonnet-4-6";
const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";

// Impact Analytics' competitor set — retail merchandising / planning / pricing /
// forecasting / assortment / supply-chain software. The model may also flag any
// other clear category rival it finds with a real source.
const COMPETITORS = [
  "Blue Yonder", "o9 Solutions", "RELEX Solutions", "Oracle Retail", "SAP (IBP / Retail)",
  "Manhattan Associates", "Logility", "ToolsGroup", "Kinaxis", "Anaplan", "Aptos",
  "SymphonyAI (Symphony RetailAI)", "Nextail", "Increff", "Onebeat", "First Insight",
  "John Galt Solutions", "Antuit.ai (Zebra)", "Toolio", "Syrup Tech", "Lily AI",
  "Revionics", "Pricefx", "Competera", "Zilliant",
].join(", ");

export type Relationship = "uses" | "implementing" | "evaluating" | "selected" | "former";

export interface CompetitorFinding {
  competitor: string;
  relationship: Relationship;
  detail: string;
  url: string;
  date: string;
  confidence: "high" | "medium";
}

interface Input { company: string; domain: string }

function iso(daysAgo: number): string {
  return new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
}
function stripFences(t: string): string { return t.replace(/^\s*```(?:json)?/i, "").replace(/```\s*$/i, "").trim(); }
function jsonArray(t: string): string {
  const s = stripFences(t); const a = s.indexOf("["); const b = s.lastIndexOf("]");
  return a >= 0 && b > a ? s.slice(a, b + 1) : s;
}

const REL = new Set<Relationship>(["uses", "implementing", "evaluating", "selected", "former"]);

export async function competitorFootprint(input: Input): Promise<{ ok: boolean; findings: CompetitorFinding[]; error?: string }> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  const { company, domain } = input;
  if (!apiKey) return { ok: false, findings: [], error: "ANTHROPIC_API_KEY not configured" };
  if (!company) return { ok: false, findings: [], error: "company is required" };

  const today = iso(0);
  const recentCutoff = iso(180);
  const system = [
    `You investigate which competitor software a specific retailer uses or is evaluating, for Impact Analytics'`,
    `sales team. Today is ${today}. Target: ${company} (${domain}).`,
    ``,
    `Competitors to look for (or any other clear retail merchandising / planning / pricing / forecasting /`,
    `assortment / supply-chain software vendor): ${COMPETITORS}.`,
    ``,
    `Return VERIFIABLE findings ONLY. A finding qualifies ONLY when a specific, real web source NAMES BOTH`,
    `${company} AND the competitor in a genuine relationship. Do not infer from generic industry articles,`,
    `analyst lists, or "companies like X use Y" phrasing. Judge the retailer by its domain (${domain}) — ignore`,
    `same-named but different companies.`,
    ``,
    `relationship must be one of:`,
    `  - "selected": a dated announcement that ${company} chose the competitor (last 180 days, on/after ${recentCutoff})`,
    `  - "implementing": actively deploying/rolling out the competitor now`,
    `  - "evaluating": RFP, pilot, or public evaluation of the competitor`,
    `  - "uses": confirmed current customer (case study, the vendor's client list, a job post requiring that tool,`,
    `     a press release) — the source may be older than 180 days for established usage`,
    `  - "former": publicly replaced/left the competitor`,
    ``,
    `Rules:`,
    `- Every finding MUST include a real "url" returned by web search and its "date". NEVER invent a url or date.`,
    `- confidence "high" only for the vendor's/${company}'s own announcement, a named case study, or major press.`,
    `  Use "medium" for a single job post, third-party blog, or indirect mention. Never include anything weaker.`,
    `- One finding per competitor per relationship. Prefer the strongest, most recent source.`,
    `- If you cannot verify any competitor relationship, return an empty array [].`,
    `- Return ONLY a JSON array, no preamble, no markdown fences. Each object:`,
    `  { "competitor": string, "relationship": "uses|implementing|evaluating|selected|former",`,
    `    "detail": one sentence <=160 chars quoting/paraphrasing the source, "url": string, "date": "YYYY-MM-DD",`,
    `    "confidence": "high|medium" }`,
  ].join("\n");

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 85_000);
    let res: Response;
    try {
      res = await fetch(ANTHROPIC_URL, {
        method: "POST",
        signal: controller.signal,
        headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
        body: JSON.stringify({
          model: MODEL,
          max_tokens: 2500,
          system,
          tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 6 }],
          messages: [{ role: "user", content: `Find competitor-software evidence for ${company} (${domain}). Return the JSON array now.` }],
        }),
      });
    } finally { clearTimeout(timer); }
    if (!res.ok) return { ok: false, findings: [], error: `Anthropic HTTP ${res.status}` };

    const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
    const text = (data.content ?? []).filter((b) => b.type === "text" && typeof b.text === "string").map((b) => b.text as string).join("\n");
    let raw: unknown;
    try { raw = JSON.parse(jsonArray(text)); } catch { return { ok: false, findings: [], error: "parse error" }; }
    if (!Array.isArray(raw)) return { ok: true, findings: [] };

    const findings: CompetitorFinding[] = [];
    const seen = new Set<string>();
    for (const r of raw as Array<Record<string, unknown>>) {
      const competitor = String(r.competitor ?? "").trim();
      const url = String(r.url ?? "").trim();
      const rel = String(r.relationship ?? "").trim().toLowerCase() as Relationship;
      // Accuracy gate: require a real http(s) url and a valid relationship.
      if (!competitor || !/^https?:\/\//i.test(url) || !REL.has(rel)) continue;
      const key = `${competitor.toLowerCase()}|${rel}`;
      if (seen.has(key)) continue;
      seen.add(key);
      findings.push({
        competitor,
        relationship: rel,
        detail: String(r.detail ?? "").slice(0, 200),
        url,
        date: String(r.date ?? ""),
        confidence: r.confidence === "high" ? "high" : "medium",
      });
    }
    // Strongest first: selected/implementing/evaluating outrank uses/former; high before medium.
    const relRank: Record<Relationship, number> = { selected: 0, implementing: 1, evaluating: 2, uses: 3, former: 4 };
    findings.sort((a, b) =>
      (a.confidence === b.confidence ? 0 : a.confidence === "high" ? -1 : 1) || relRank[a.relationship] - relRank[b.relationship],
    );
    return { ok: true, findings };
  } catch (e) {
    return { ok: false, findings: [], error: (e as Error).message };
  }
}
