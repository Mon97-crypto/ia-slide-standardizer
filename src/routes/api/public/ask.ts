/**
 * ask.ts — "Ask IAsense". Answers a free-form question about any company/news
 * using Claude with live web search. Returns a concise, sourced answer.
 * Guarded by ANTHROPIC_API_KEY. Never throws.
 */

const MODEL = process.env.SCAN_NEWS_MODEL || "claude-sonnet-4-6";
const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";

interface AskInput {
  question: string;
  company?: string;
  domain?: string;
  /** Compact Salesforce CRM context (owner/BD/status/revenue for relevant accounts). */
  crm?: string;
}

export interface AskResult {
  ok: boolean;
  answer?: string;
  sources?: { title: string; url: string }[];
  error?: string;
}

export async function ask(input: AskInput): Promise<AskResult> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  try {
    if (!apiKey) return { ok: false, error: "ANTHROPIC_API_KEY is not configured on the server." };
    const question = (input.question || "").trim();
    if (!question) return { ok: false, error: "A question is required." };

    const ctx = input.company
      ? `The user is asking about ${input.company}${input.domain ? ` (${input.domain})` : ""}. Only use sources about that specific company.`
      : "";

    const crm = (input.crm || "").trim();
    const crmBlock = crm
      ? [
          "You also have INTERNAL Salesforce CRM data from Impact Analytics' own records (below). Treat it as authoritative ground truth for account ownership, BD owner, account type, status, revenue and Tier 1 flags — prefer it over the web for those facts, and cite it as \"per Impact Analytics CRM\" (no URL needed). Use web search for external/market news and blend the two.",
          "",
          "── Salesforce CRM data ──",
          crm,
          "──",
          "",
        ].join("\n")
      : "";

    const system = [
      "You are IAsense, a retail sales-intelligence assistant for Impact Analytics (an AI-native retail decisioning platform).",
      "Answer the user's question using current web search AND the internal CRM data provided. Prioritise recent, dated facts. Never invent data, quotes, metrics or URLs — drop anything you cannot verify.",
      ctx,
      "",
      crmBlock,
      "Format the answer as a clean, skimmable briefing in GitHub-flavoured MARKDOWN, following this house structure:",
      "1. A one or two sentence framing intro (no heading) that leads with the direct answer.",
      "2. `## Key takeaways` — 3 to 5 bullets. Each bullet = a claim, then why it matters for a retail-planning sales conversation. Put the most important first. Bold the key phrase.",
      "3. Then `## <themed section>` headings as needed (e.g. Leadership, Operations, Technology, Financials) — short paragraphs, each stating the dated fact then the implication.",
      "4. End with `## Sources` — a bulleted list of the sources you used as markdown links `[Title](url)`.",
      "",
      "Rules: direct, active voice; lead with the insight, then context; short paragraphs; dates on facts.",
      "Use inline markdown links `[text](url)` when you reference a source in the body.",
      "Do not use these filler words: leverage, synergy, robust, streamline, seamless, cutting-edge, delve, innovative.",
      "If the week/topic is quiet or you found little, say so plainly rather than padding.",
    ].filter(Boolean).join("\n");

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
          max_tokens: 2200,
          system,
          tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 6 }],
          messages: [{ role: "user", content: question }],
        }),
      });
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return { ok: false, error: `Anthropic HTTP ${res.status}: ${body.slice(0, 160)}` };
    }

    const data = (await res.json()) as {
      content?: Array<{ type: string; text?: string; content?: Array<{ type: string; title?: string; url?: string }> }>;
    };
    const answer = (data.content ?? [])
      .filter((b) => b.type === "text" && typeof b.text === "string")
      .map((b) => b.text as string)
      .join("\n")
      .trim();

    // Collect web-search result URLs as sources.
    const sources: { title: string; url: string }[] = [];
    for (const block of data.content ?? []) {
      if (block.type === "web_search_tool_result" && Array.isArray(block.content)) {
        for (const r of block.content) {
          if (r.url) sources.push({ title: r.title ?? r.url, url: r.url });
        }
      }
    }

    return { ok: true, answer: answer || "No answer returned.", sources: sources.slice(0, 8) };
  } catch (err) {
    return { ok: false, error: (err as Error).message };
  }
}
