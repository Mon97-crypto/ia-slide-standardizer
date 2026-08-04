/**
 * SignalTile — a detected signal as a card (ported from the reference design):
 * a colored left bar by tone, glyph + label, category badge, the detail line, the
 * "so what" + IA products, status/confidence/date pills, and the evidence link.
 * Cards lift on hover and stagger in.
 */
import type { ScoredSignal } from "../lib/scan";

function toneFor(s: ScoredSignal): string {
  if (!s.found) return "var(--ia-gray-2)";
  if (s.type === "negative") return "var(--ia-orange)";
  if (s.type === "positive") return "var(--ia-blue)";
  return "var(--ia-gray-3)";
}

function toneBg(tone: string): string {
  if (tone === "var(--ia-orange)") return "#fff1e8";
  if (tone === "var(--ia-blue)") return "var(--ia-blue-soft)";
  return "var(--ia-offwhite)";
}

function categoryLabel(type: ScoredSignal["type"]): string {
  if (type === "positive") return "Positive";
  if (type === "negative") return "Negative";
  return "Mixed";
}

function confidenceFor(s: ScoredSignal): "High" | "Medium" | "Low" {
  if (s.evidence.length >= 2) return "High";
  if (s.evidence.length === 1) return "Medium";
  return "Low";
}

function sourceName(url: string): string {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    const base = host.split(".")[0] ?? host;
    return base.charAt(0).toUpperCase() + base.slice(1);
  } catch {
    return "Source";
  }
}

/** Drop the trailing "lead with …" clause — the products are shown separately. */
function cleanSoWhat(text: string): string {
  let t = text.replace(/\s*[;.]\s*lead with[^.]*\.?\s*$/i, "").trim();
  if (t && !/[.!?]$/.test(t)) t += ".";
  return t;
}

/** The most relevant products: those named in the "lead with" guidance, else the
 * signal's top curated products. Capped so the tile names only what matters. */
function relevantProducts(soWhat: string, iaProducts: string[]): string[] {
  if (!iaProducts.length) return [];
  const named = iaProducts.filter((p) =>
    new RegExp(`\\b${p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i").test(soWhat || ""),
  );
  return (named.length ? named : iaProducts).slice(0, 3);
}

export function SignalTile({ signal, index }: { signal: ScoredSignal; index: number }) {
  const tone = toneFor(signal);
  const bg = toneBg(tone);
  const ev = signal.evidence[0];

  return (
    <div
      className="hover-lift"
      style={{
        position: "relative",
        overflow: "hidden",
        borderRadius: 16,
        border: "1px solid var(--ia-gray-1)",
        background: "var(--ia-white)",
        padding: "16px 18px",
        animation: "row-in 320ms cubic-bezier(.22,.61,.36,1) both",
        animationDelay: `${Math.min(index, 12) * 60}ms`,
      }}
    >
      <span aria-hidden style={{ position: "absolute", top: 0, bottom: 0, left: 0, width: 3, background: tone }} />

      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <span aria-hidden style={{ color: tone }}>{signal.glyph}</span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{signal.label}</span>
        </span>
        <span style={{ flexShrink: 0, borderRadius: 999, padding: "2px 8px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", background: bg, color: tone }}>
          {categoryLabel(signal.type)}
        </span>
      </div>

      <p style={{ margin: "8px 0 0", fontSize: 15, fontWeight: 500, lineHeight: 1.45, color: "var(--ia-black)" }}>{signal.detail}</p>

      {signal.soWhat && (() => {
        const clean = cleanSoWhat(signal.soWhat);
        const products = relevantProducts(signal.soWhat, signal.iaProducts ?? []);
        return (
          <p className="secondary" style={{ margin: "5px 0 0", fontSize: 13, lineHeight: 1.5 }}>
            {clean}
            {products.length > 0 && (
              <>
                {clean ? " · " : ""}
                <span style={{ color: "var(--ia-black)", fontWeight: 600 }}>{products.join(", ")}</span>
              </>
            )}
          </p>
        );
      })()}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
        <span className="label" style={{ borderRadius: 999, padding: "2px 9px", fontSize: 11, fontWeight: 600, background: bg, color: tone }}>Detected</span>
        <span className="label" style={{ borderRadius: 999, padding: "2px 9px", fontSize: 11, background: "var(--ia-offwhite)", color: "var(--ia-gray-3)" }}>Confidence: {confidenceFor(signal)}</span>
        {ev?.date && (
          <span className="label" style={{ borderRadius: 999, padding: "2px 9px", fontSize: 11, border: "1px solid var(--ia-gray-1)", color: "var(--ia-gray-3)" }}>{ev.date}</span>
        )}
      </div>

      {ev?.url && (
        <p className="secondary" style={{ marginTop: 8, fontSize: 13 }}>
          Evidence:{" "}
          <a href={ev.url} target="_blank" rel="noreferrer" style={{ fontWeight: 500 }}>{sourceName(ev.url)} ↗</a>
          {ev.date ? <span style={{ color: "var(--ia-gray-2)" }}> · {ev.date}</span> : null}
        </p>
      )}
    </div>
  );
}
