/**
 * CompetitorFootprint — on-demand panel showing VERIFIABLE public evidence that a
 * target retailer uses / is evaluating / recently selected an Impact Analytics
 * competitor. Every finding shows the relationship, a confidence level and a
 * source link so a rep can verify it. Fetches only on click (uses credits).
 */
import { useState } from "react";

type Relationship = "uses" | "implementing" | "evaluating" | "selected" | "former";
interface Finding {
  competitor: string;
  relationship: Relationship;
  detail: string;
  url: string;
  date: string;
  confidence: "high" | "medium";
}

const REL_LABEL: Record<Relationship, string> = {
  selected: "Recently selected",
  implementing: "Implementing",
  evaluating: "Evaluating",
  uses: "Current customer",
  former: "Former customer",
};
// selected/implementing/evaluating = active displacement urgency (orange);
// uses = incumbent to displace (blue); former = white space (green).
function relTone(r: Relationship): { bg: string; color: string } {
  if (r === "former") return { bg: "#e9f7ef", color: "#1e7e49" };
  if (r === "uses") return { bg: "var(--ia-blue-soft)", color: "var(--ia-blue-dark)" };
  return { bg: "#fff1e8", color: "var(--ia-orange)" };
}

function hostOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return "source"; }
}

export function CompetitorFootprint({ company, domain }: { company: string; domain: string }) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [error, setError] = useState("");

  async function run() {
    setState("loading");
    try {
      const res = await fetch("/api/public/competitor-footprint", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ company, domain }),
      });
      const data = (await res.json()) as { ok: boolean; findings?: Finding[]; error?: string };
      if (!data.ok) { setError(data.error || "Could not check."); setState("error"); return; }
      setFindings(data.findings ?? []);
      setState("done");
    } catch (e) {
      setError((e as Error).message); setState("error");
    }
  }

  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="eyebrow">Competitor footprint</div>
          <div className="secondary" style={{ fontSize: 13, marginTop: 2 }}>
            Public evidence of competitor tools — displacement signals, each with a source you can verify.
          </div>
        </div>
        {state === "idle" && <button onClick={run} style={btnPrimary}>Check competitor footprint</button>}
        {state === "loading" && (
          <span className="secondary" style={{ fontSize: 13, display: "inline-flex", alignItems: "center", gap: 7 }}>
            <span aria-hidden style={{ width: 7, height: 7, borderRadius: 999, background: "var(--ia-blue)", animation: "pulse 1s ease-in-out infinite" }} />
            Searching public sources…
          </span>
        )}
        {(state === "done" || state === "error") && <button onClick={run} style={btnGhost}>Re-check</button>}
      </div>

      {state === "idle" && (
        <p className="secondary" style={{ fontSize: 12, marginTop: 10, marginBottom: 0 }}>
          Runs a live web search (uses Anthropic credits). Only reports competitors named in a real, dated source
          alongside {company} — no guesses.
        </p>
      )}

      {state === "error" && <div style={{ marginTop: 12, color: "var(--ia-orange)", fontSize: 14 }}>{error}</div>}

      {state === "done" && (
        <div style={{ marginTop: 14 }}>
          {findings.length === 0 ? (
            <div className="secondary" style={{ fontSize: 14 }}>
              No verifiable competitor relationships found in public sources for {company}. That's often a green-field
              signal — but absence of public evidence isn't proof they use nothing.
            </div>
          ) : (
            <div style={{ display: "grid", gap: 10 }}>
              {findings.map((f, i) => {
                const tone = relTone(f.relationship);
                return (
                  <div key={i} style={{ border: "1px solid var(--ia-gray-1)", borderRadius: 12, padding: "12px 14px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                      <span style={{ fontWeight: 700 }}>{f.competitor}</span>
                      <span className="label" style={{ padding: "2px 9px", borderRadius: 999, background: tone.bg, color: tone.color, fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" }}>{REL_LABEL[f.relationship]}</span>
                      <span className="label" style={{ padding: "2px 8px", borderRadius: 999, background: f.confidence === "high" ? "var(--ia-blue-soft)" : "var(--ia-offwhite)", color: f.confidence === "high" ? "var(--ia-blue-dark)" : "var(--ia-gray-3)", fontSize: 11, fontWeight: 600 }}>{f.confidence} confidence</span>
                      {f.date && <span className="secondary" style={{ fontSize: 12 }}>{f.date}</span>}
                    </div>
                    {f.detail && <div style={{ fontSize: 14, color: "var(--ia-black)" }}>{f.detail}</div>}
                    <a href={f.url} target="_blank" rel="noreferrer" style={{ fontSize: 13, color: "var(--ia-blue)", textDecoration: "none", fontWeight: 600 }}>
                      Source · {hostOf(f.url)} ↗
                    </a>
                  </div>
                );
              })}
              <p className="secondary" style={{ fontSize: 12, margin: "2px 0 0" }}>
                Every finding is cited — open the source to confirm before you act on it.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const btnPrimary: React.CSSProperties = { height: 36, padding: "0 16px", borderRadius: 11, border: "none", background: "var(--ia-blue)", color: "#fff", fontWeight: 600, fontSize: 14 };
const btnGhost: React.CSSProperties = { height: 34, padding: "0 14px", borderRadius: 10, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 13 };
