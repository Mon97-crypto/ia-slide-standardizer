/**
 * AskView — "Ask IAsense". Free-form questions about any company/news, answered
 * by Claude with live web search. Keeps a simple running thread.
 */
import { useRef, useState } from "react";
import { Markdown } from "../components/Markdown";

interface Turn {
  q: string;
  a?: string;
  sources?: { title: string; url: string }[];
  error?: string;
  loading?: boolean;
}

export function AskView() {
  const [question, setQuestion] = useState("");
  const [company, setCompany] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const busy = turns.some((t) => t.loading);
  const ref = useRef<HTMLInputElement>(null);

  async function ask() {
    const q = question.trim();
    if (!q || busy) return;
    const idx = turns.length;
    setTurns((t) => [...t, { q, loading: true }]);
    setQuestion("");
    try {
      const res = await fetch("/api/public/ask", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: q, company: company.trim() || undefined }),
      });
      const data = (await res.json()) as { ok: boolean; answer?: string; sources?: { title: string; url: string }[]; error?: string };
      setTurns((t) => t.map((turn, i) => i === idx ? { q, a: data.answer, sources: data.sources, error: data.ok ? undefined : data.error, loading: false } : turn));
    } catch (e) {
      setTurns((t) => t.map((turn, i) => i === idx ? { q, error: (e as Error).message, loading: false } : turn));
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Ask IAsense · account intelligence</div>
        <h1 className="h1" style={{ margin: 0 }}>Ask about any <span className="accent">account</span>.</h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 620 }}>
          Ask a question about any company's news, leadership, operations or vendors. IAsense researches the web
          live and answers with dated, sourced facts — and now also draws on your connected Salesforce accounts
          (owner, BD owner, type, status, revenue, Tier 1) for internal questions.
        </p>
      </div>

      <section className="card" style={{ padding: 20, marginBottom: 24 }}>
        <form onSubmit={(e) => { e.preventDefault(); ask(); }} style={{ display: "grid", gap: 12 }}>
          <label style={{ display: "grid", gap: 6 }}>
            <span className="eyebrow">Company focus (optional)</span>
            <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Gap" style={inputStyle} />
          </label>
          <label style={{ display: "grid", gap: 6 }}>
            <span className="eyebrow">Question</span>
            <input ref={ref} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What's the latest on their inventory or leadership?" style={inputStyle} autoFocus />
          </label>
          <div><button type="submit" disabled={busy} style={btnStyle(busy)}>{busy ? "Researching…" : "Ask"}</button></div>
        </form>
      </section>

      <div style={{ display: "grid", gap: 16 }}>
        {[...turns].reverse().map((t, i) => (
          <div key={turns.length - 1 - i} className="card" style={{ padding: 20 }}>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>{t.q}</div>
            {t.loading && <span className="secondary">Researching the web…</span>}
            {t.error && <span style={{ color: "var(--ia-orange)" }}>{t.error}{t.error.includes("ANTHROPIC_API_KEY") ? " — set it on the server." : ""}</span>}
            {t.a && <Markdown text={t.a} />}
          </div>
        ))}
        {turns.length === 0 && (
          <div style={{ textAlign: "center", padding: "40px 0", color: "var(--ia-gray-3)" }}>
            <p className="secondary">Ask anything — e.g. "Has Target had inventory problems this year?"</p>
          </div>
        )}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = { height: 44, padding: "0 14px", borderRadius: 13, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", fontSize: 15, fontFamily: "inherit", color: "var(--ia-black)" };
function btnStyle(disabled: boolean): React.CSSProperties {
  return { height: 44, padding: "0 22px", borderRadius: 13, border: "none", background: disabled ? "var(--ia-blue-light)" : "var(--ia-blue)", color: "var(--ia-white)", fontWeight: 600, fontSize: 15 };
}
