/**
 * digest-provider.ts — for the admin "top accounts" digest. One Claude web-search
 * call per person that finds developments from the LAST 7 DAYS ONLY across that
 * person's Tier 1 accounts, returned as compact items the client can dedup and
 * render into a weekly digest. Never throws.
 */

const MODEL = process.env.SCAN_NEWS_MODEL || "claude-sonnet-4-6";
const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";

export interface DigestItem {
  account: string;
  domain: string;
  headline: string;
  detail: string;
  soWhat: string;
  url: string;
  date: string;
}

interface AcctInput { name: string; domain: string }

function iso(daysAgo: number): string {
  return new Date(Date.now() - daysAgo * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
}
function stripFences(t: string): string {
  return t.replace(/^\s*```(?:json)?/i, "").replace(/```\s*$/i, "").trim();
}
function jsonArray(t: string): string {
  const s = stripFences(t);
  const a = s.indexOf("["); const b = s.lastIndexOf("]");
  return a >= 0 && b > a ? s.slice(a, b + 1) : s;
}

export interface RollupHighlight {
  account: string;
  domain: string;
  headline: string;
  detail: string;
  whyItMatters: string;
  url: string;
  date: string;
}

function jsonObject(t: string): string {
  const s = stripFences(t);
  const a = s.indexOf("{"); const b = s.lastIndexOf("}");
  return a >= 0 && b > a ? s.slice(a, b + 1) : s;
}

/** Executive roll-up across the whole Tier 1 book (for CXOs): a short portfolio
 * overview + the most significant last-7-day developments, each cited. */
export async function execRollup(accounts: AcctInput[]): Promise<{ ok: boolean; overview: string; highlights: RollupHighlight[]; error?: string }> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return { ok: false, overview: "", highlights: [], error: "ANTHROPIC_API_KEY not configured" };
  const list = accounts.filter((a) => a.name || a.domain).slice(0, 30);
  if (!list.length) return { ok: true, overview: "", highlights: [] };

  const today = iso(0);
  const cutoff = iso(7);
  const companies = list.map((a) => `- ${a.name} (${a.domain})`).join("\n");
  const system = [
    `You write a concise EXECUTIVE roll-up for the Impact Analytics leadership team (CXOs), summarising activity`,
    `across the sales team's Tier 1 target accounts. Today is ${today}.`,
    ``,
    `Look for the MOST SIGNIFICANT developments in the LAST 7 DAYS ONLY (on/after ${cutoff}) across these accounts:`,
    `leadership changes, M&A, major expansion or store moves, inventory/markdown/supply-chain pain, ERP/planning/`,
    `vendor decisions, earnings surprises, layoffs/restructuring, funding. Prioritise items with clear pipeline or`,
    `strategic relevance to Impact Analytics; skip minor noise.`,
    ``,
    `Rules:`,
    `- Only include a highlight with a REAL, dated source from the last 7 days. Never invent a url or date.`,
    `- Judge each company by its domain; ignore same-named but different companies.`,
    `- Rank highlights by significance; return 5–10 (fewer if the week was quiet).`,
    `- Return ONLY a JSON object, no preamble, no markdown fences:`,
    `  { "overview": 2–4 sentence executive summary of the week across the portfolio,`,
    `    "highlights": [ { "account": exact name from the list, "headline": <=80 chars,`,
    `      "detail": one sentence <=200 chars, "whyItMatters": one sentence <=180 chars on the strategic/pipeline`,
    `      implication for Impact Analytics, "url": string, "date": "YYYY-MM-DD" } ] }`,
    `- If almost nothing happened, say so in "overview" and return few or no highlights.`,
    ``,
    `Accounts:`,
    companies,
  ].join("\n");

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 110_000);
    let res: Response;
    try {
      res = await fetch(ANTHROPIC_URL, {
        method: "POST",
        signal: controller.signal,
        headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
        body: JSON.stringify({
          model: MODEL,
          max_tokens: 3500,
          system,
          tools: [{ type: "web_search_20250305", name: "web_search", max_uses: Math.min(10, Math.max(5, Math.round(list.length / 3))) }],
          messages: [{ role: "user", content: `Research the last 7 days across these ${list.length} Tier 1 accounts and return the executive roll-up JSON object now.` }],
        }),
      });
    } finally { clearTimeout(timer); }
    if (!res.ok) return { ok: false, overview: "", highlights: [], error: `Anthropic HTTP ${res.status}` };
    const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
    const text = (data.content ?? []).filter((b) => b.type === "text" && typeof b.text === "string").map((b) => b.text as string).join("\n");
    let obj: Record<string, unknown>;
    try { obj = JSON.parse(jsonObject(text)) as Record<string, unknown>; } catch { return { ok: false, overview: "", highlights: [], error: "parse error" }; }

    const byName = new Map(list.map((a) => [a.name.toLowerCase(), a.domain]));
    const rawH = Array.isArray(obj.highlights) ? (obj.highlights as Array<Record<string, unknown>>) : [];
    const highlights: RollupHighlight[] = [];
    for (const r of rawH) {
      const account = String(r.account ?? "").trim();
      const url = String(r.url ?? "").trim();
      if (!account || !/^https?:\/\//i.test(url)) continue;
      highlights.push({
        account,
        domain: byName.get(account.toLowerCase()) ?? "",
        headline: String(r.headline ?? "").slice(0, 100),
        detail: String(r.detail ?? "").slice(0, 240),
        whyItMatters: String(r.whyItMatters ?? "").slice(0, 220),
        url,
        date: String(r.date ?? ""),
      });
    }
    return { ok: true, overview: String(obj.overview ?? "").slice(0, 900), highlights };
  } catch (e) {
    return { ok: false, overview: "", highlights: [], error: (e as Error).message };
  }
}

export async function personDigest(personName: string, accounts: AcctInput[]): Promise<{ ok: boolean; items: DigestItem[]; error?: string }> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return { ok: false, items: [], error: "ANTHROPIC_API_KEY not configured" };
  const list = accounts.filter((a) => a.name || a.domain).slice(0, 20);
  if (!list.length) return { ok: true, items: [] };

  const today = iso(0);
  const cutoff = iso(7);
  const companies = list.map((a) => `- ${a.name} (${a.domain})`).join("\n");
  const system = [
    `You research VERY RECENT, sales-relevant developments for a set of retail companies,`,
    `on behalf of Impact Analytics (retail AI for planning, pricing, inventory, assortment).`,
    `Today is ${today}. For each company below, find developments dated in the LAST 7 DAYS ONLY`,
    `(on or after ${cutoff}) that a sales rep would care about: leadership changes, M&A,`,
    `store or geographic expansion, inventory / markdown / forecasting / supply-chain pain,`,
    `ERP / planning / tech migrations, layoffs or restructuring, funding, earnings, new initiatives.`,
    ``,
    `Rules:`,
    `- Only include an item when you have a REAL, dated source from the last 7 days (on/after ${cutoff}).`,
    `  If a company has nothing qualifying in the last 7 days, include NOTHING for it. Do not pad.`,
    `- Every item must cite a real url returned by web search. Never invent a url or a date.`,
    `- Judge the company by its domain; ignore same-named but different companies.`,
    `- Return ONLY a JSON array, no preamble, no markdown fences. Each object:`,
    `  { "account": <the exact company name from the list>, "headline": string <=70 chars,`,
    `    "detail": one sentence <=180 chars, "soWhat": one sentence <=160 chars on why it matters`,
    `    for outreach, "url": string, "date": "YYYY-MM-DD" }`,
    `- If nothing qualifies for any company, return [].`,
    ``,
    `Companies:`,
    companies,
  ].join("\n");

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90_000);
    let res: Response;
    try {
      res = await fetch(ANTHROPIC_URL, {
        method: "POST",
        signal: controller.signal,
        headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
        body: JSON.stringify({
          model: MODEL,
          max_tokens: 3500,
          system,
          tools: [{ type: "web_search_20250305", name: "web_search", max_uses: Math.min(8, Math.max(3, list.length)) }],
          messages: [{ role: "user", content: `Research these ${list.length} companies for last-7-day developments (${personName}'s accounts) and return the JSON array now.` }],
        }),
      });
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) return { ok: false, items: [], error: `Anthropic HTTP ${res.status}` };
    const data = (await res.json()) as { content?: Array<{ type: string; text?: string }> };
    const text = (data.content ?? []).filter((b) => b.type === "text" && typeof b.text === "string").map((b) => b.text as string).join("\n");
    let raw: unknown;
    try { raw = JSON.parse(jsonArray(text)); } catch { return { ok: false, items: [], error: "parse error" }; }
    if (!Array.isArray(raw)) return { ok: true, items: [] };

    const byName = new Map(list.map((a) => [a.name.toLowerCase(), a.domain]));
    const items: DigestItem[] = [];
    for (const r of raw as Array<Record<string, unknown>>) {
      const account = String(r.account ?? "").trim();
      const url = String(r.url ?? "").trim();
      if (!account || !url) continue;
      items.push({
        account,
        domain: byName.get(account.toLowerCase()) ?? "",
        headline: String(r.headline ?? "").slice(0, 90),
        detail: String(r.detail ?? "").slice(0, 220),
        soWhat: String(r.soWhat ?? "").slice(0, 200),
        url,
        date: String(r.date ?? ""),
      });
    }
    return { ok: true, items };
  } catch (e) {
    return { ok: false, items: [], error: (e as Error).message };
  }
}
