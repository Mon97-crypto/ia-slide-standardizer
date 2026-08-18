/**
 * SignalRow — the core of the product, tuned hardest. 44px tall at rest: glyph,
 * name, signed contribution, and a one-line detail truncated with an ellipsis.
 * Rows with evidence expand in place on click (never a modal). Fully keyboard
 * operable. Color is never the only cue — every row carries a glyph and the sign
 * of its contribution as text, so it reads in grayscale and for colorblind users.
 */
import { useState } from "react";
import type { ScoredSignal } from "../lib/scan";

function colorFor(s: ScoredSignal): string {
  if (!s.found) return "var(--ia-gray-3)";
  if (s.type === "positive") return "var(--ia-blue)";
  if (s.type === "negative") return "var(--ia-orange)";
  return "var(--ia-gray-3)"; // neutral
}

export function SignalRow({ signal, index }: { signal: ScoredSignal; index: number }) {
  const [open, setOpen] = useState(false);
  const hasEvidence = signal.evidence.length > 0;
  const hasDetail = hasEvidence || (signal.soWhat && signal.soWhat.length > 0);
  const expandable = signal.found && hasDetail;
  const [hover, setHover] = useState(false);
  const color = colorFor(signal);
  const signed =
    signal.score_contribution === 0
      ? "0"
      : `${signal.score_contribution > 0 ? "+" : ""}${signal.score_contribution}`;

  return (
    <div
      style={{
        borderTop: index === 0 ? "none" : "1px solid var(--ia-gray-1)",
        background: hover && expandable ? "var(--ia-blue-soft)" : "transparent",
        transition: "background 180ms cubic-bezier(.22,.61,.36,1)",
        animation: "row-in 180ms cubic-bezier(.22,.61,.36,1) both",
        animationDelay: `${index * 30}ms`,
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div
        role={expandable ? "button" : undefined}
        tabIndex={expandable ? 0 : undefined}
        aria-expanded={expandable ? open : undefined}
        onClick={() => expandable && setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (expandable && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
        style={{
          minHeight: 44,
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "0 14px",
          cursor: expandable ? "pointer" : "default",
        }}
      >
        <span
          aria-hidden
          className="tnum"
          style={{ color, width: 16, textAlign: "center", fontSize: 14, opacity: signal.found ? 1 : 0.5 }}
        >
          {signal.glyph}
        </span>

        <span
          style={{
            fontWeight: signal.found ? 500 : 400,
            color: signal.found ? "var(--ia-black)" : "var(--ia-gray-3)",
            width: 220,
            flexShrink: 0,
          }}
        >
          {signal.label}
        </span>

        <span
          className="tnum label"
          style={{
            color,
            width: 44,
            flexShrink: 0,
            fontWeight: 600,
          }}
        >
          {signal.found ? signed : "—"}
        </span>

        <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", justifyContent: "center", gap: 1, paddingBlock: 6 }}>
          <span
            className="secondary"
            style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
          >
            {signal.detail}
          </span>
          {signal.found && signal.soWhat && (
            <span
              className="label"
              style={{
                color: "var(--ia-blue-dark)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                opacity: 0.85,
              }}
            >
              {signal.soWhat}
            </span>
          )}
        </span>

        {expandable && (
          <span aria-hidden className="secondary" style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 180ms cubic-bezier(.22,.61,.36,1)" }}>
            ›
          </span>
        )}
      </div>

      {open && expandable && (
        <div style={{ padding: "0 14px 14px 42px" }}>
          {signal.soWhat && (
            <p className="secondary" style={{ margin: "0 0 8px", color: "var(--ia-black)" }}>
              {signal.soWhat}
            </p>
          )}
          {signal.iaProducts && signal.iaProducts.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
              {signal.iaProducts.map((p) => (
                <span
                  key={p}
                  className="label"
                  style={{
                    padding: "2px 8px",
                    borderRadius: 999,
                    background: "var(--ia-blue-soft)",
                    color: "var(--ia-blue-dark)",
                  }}
                >
                  {p}
                </span>
              ))}
            </div>
          )}
          {signal.evidence.length > 0 && (
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 6 }}>
              {signal.evidence.map((e, i) => (
                <li key={i} className="secondary">
                  <a href={e.url} target="_blank" rel="noreferrer">
                    {e.title || e.url}
                  </a>
                  {e.date && <span className="tnum" style={{ marginLeft: 8, color: "var(--ia-gray-3)" }}>{e.date}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
