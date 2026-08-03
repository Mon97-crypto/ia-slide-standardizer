/**
 * SignalSpectrum — the one bold element on the page. A single horizontal track
 * running from risk (left) to opportunity (right). Every detected signal is a
 * tick at its weighted position; the account's score sits on the track as a
 * solid marker. Score and composition in one glance, which a ring cannot do.
 *
 * Below 640px the track becomes vertical.
 */
import { useEffect, useState } from "react";
import type { IntentLevel, ScoredSignal } from "../lib/scan";

const DOMAIN = 60; // track spans [-60 (risk) .. +60 (opportunity)]

function pct(value: number): number {
  const clamped = Math.max(-DOMAIN, Math.min(DOMAIN, value));
  return ((clamped + DOMAIN) / (2 * DOMAIN)) * 100;
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

function useVertical(): boolean {
  const [vertical, setVertical] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    setVertical(mq.matches);
    const on = () => setVertical(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return vertical;
}

interface Props {
  signals: ScoredSignal[];
  total: number;
  intent: IntentLevel;
}

export function SignalSpectrum({ signals, total, intent }: Props) {
  const reduced = useReducedMotion();
  const vertical = useVertical();
  const [drawn, setDrawn] = useState(reduced);

  useEffect(() => {
    if (reduced) {
      setDrawn(true);
      return;
    }
    setDrawn(false);
    const id = requestAnimationFrame(() => setDrawn(true));
    return () => cancelAnimationFrame(id);
  }, [reduced, signals]);

  const ticks = signals
    .filter((s) => s.found && s.score_contribution !== 0)
    .map((s) => ({
      key: s.name,
      value: s.score_contribution,
      weight: s.weight,
      risk: s.score_contribution < 0,
      label: s.label,
    }));

  // Ticks draw left → right; order by position so the sweep reads naturally.
  const ordered = [...ticks].sort((a, b) => pct(a.value) - pct(b.value));
  const markerPct = pct(total);

  const trackStyle: React.CSSProperties = vertical
    ? { position: "relative", width: 10, height: 320, margin: "0 auto" }
    : { position: "relative", height: 10, width: "100%" };

  return (
    <div>
      <div
        role="img"
        aria-label={`Signal spectrum. Score ${total}, intent ${intent}.`}
        style={{ padding: vertical ? "8px 0" : "28px 0 8px" }}
      >
        <div
          style={{
            ...trackStyle,
            background: "var(--ia-offwhite)",
            border: "1px solid var(--ia-gray-1)",
            borderRadius: 999,
          }}
        >
          {/* subtle centre (neutral) reference line */}
          <span
            aria-hidden
            style={{
              position: "absolute",
              background: "var(--ia-gray-2)",
              ...(vertical
                ? { left: -3, right: -3, top: "50%", height: 1 }
                : { top: -3, bottom: -3, left: "50%", width: 1 }),
            }}
          />

          {ordered.map((t, i) => {
            const size = 10 + t.weight * 0.55; // sized by weight
            const p = pct(t.value);
            const common: React.CSSProperties = {
              position: "absolute",
              background: t.risk ? "var(--ia-orange)" : "var(--ia-blue)",
              borderRadius: 2,
              opacity: drawn ? 1 : 0,
              transition: reduced
                ? "none"
                : `opacity 180ms cubic-bezier(.22,.61,.36,1) ${i * 22}ms`,
            };
            return (
              <span
                key={t.key}
                title={`${t.label} ${t.value > 0 ? "+" : ""}${t.value}`}
                style={
                  vertical
                    ? {
                        ...common,
                        width: size,
                        height: 3,
                        left: `calc(50% - ${size / 2}px)`,
                        bottom: `calc(${p}% - 1.5px)`,
                      }
                    : {
                        ...common,
                        height: size,
                        width: 3,
                        top: `calc(50% - ${size / 2}px)`,
                        left: `calc(${p}% - 1.5px)`,
                      }
                }
              />
            );
          })}

          {/* Position marker — solid Impact Blue. */}
          <span
            aria-hidden
            style={{
              position: "absolute",
              width: 16,
              height: 16,
              borderRadius: 999,
              background: "var(--ia-blue)",
              border: "3px solid var(--ia-white)",
              boxShadow: "0 1px 6px rgba(38,76,215,.35)",
              transition: reduced
                ? "none"
                : "left 600ms cubic-bezier(.22,.61,.36,1) 400ms, bottom 600ms cubic-bezier(.22,.61,.36,1) 400ms",
              ...(vertical
                ? { left: -3, bottom: `calc(${drawn ? markerPct : 50}% - 8px)` }
                : { top: -3, left: `calc(${drawn ? markerPct : 50}% - 8px)` }),
            }}
          />
        </div>

        {/* endpoints */}
        <div
          className="eyebrow"
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 12,
            ...(vertical ? { flexDirection: "column-reverse", alignItems: "center", gap: 4 } : {}),
          }}
        >
          <span style={{ color: "var(--ia-orange)" }}>Risk</span>
          <span style={{ color: "var(--ia-blue)" }}>Opportunity</span>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 8 }}>
        <span
          className="tnum"
          style={{ fontSize: 40, fontWeight: 600, lineHeight: 1, color: "var(--ia-blue)" }}
        >
          {total > 0 ? "+" : ""}
          {total}
        </span>
        <span className="serif" style={{ fontSize: 22 }}>
          {intent}
        </span>
      </div>
    </div>
  );
}
