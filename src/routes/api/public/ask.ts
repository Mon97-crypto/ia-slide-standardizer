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

    const system = [
      "You are IAsense, a retail sales-intelligence assistant for Impact Analytics (an AI-native retail decisioning platform).",
      "Answer the user's question using current web search. Prioritise recent, dated facts.",
      ctx,
      "Be concise and factual. Lead with the direct answer. Cite specific sources; never invent a URL.",
      "When relevant, note what it means for a retail-planning sales conversation, briefly.",
    ].filter(Boolean).join(" ");

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
          max_tokens: 1500,
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
