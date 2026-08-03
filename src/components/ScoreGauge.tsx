/**
 * ScoreGauge — a circular score dial, echoing the dashboard screenshots but in
 * IA brand colors (Impact Blue for opportunity, Accent Orange for risk). Maps
 * the account's total (domain [-60, 60]) onto a 0-100 arc.
 */
import type { IntentLevel } from "../lib/scan";

const DOMAIN = 60;

export function ScoreGauge({ total, intent }: { total: number; intent: IntentLevel }) {
  const pct = Math.max(0, Math.min(1, (total + DOMAIN) / (2 * DOMAIN)));
  const risk = total < 0;
  const stroke = risk ? "var(--ia-orange)" : "var(--ia-blue)";
  const r = 62;
  const circ = 2 * Math.PI * r;
  const dash = circ * 0.75; // 270° arc
  const filled = dash * pct;

  return (
    <div style={{ position: "relative", width: 168, height: 168, margin: "0 auto" }}>
      <svg width="168" height="168" viewBox="0 0 168 168" style={{ transform: "rotate(135deg)" }}>
        <circle cx="84" cy="84" r={r} fill="none" stroke="var(--ia-offwhite)" strokeWidth="12"
          strokeLinecap="round" strokeDasharray={`${dash} ${circ}`} />
        <circle cx="84" cy="84" r={r} fill="none" stroke={stroke} strokeWidth="12"
          strokeLinecap="round" strokeDasharray={`${filled} ${circ}`}
          style={{ transition: "stroke-dasharray 600ms cubic-bezier(.22,.61,.36,1) 300ms" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span className="tnum" style={{ fontSize: 44, fontWeight: 600, lineHeight: 1, color: stroke }}>
          {total > 0 ? "+" : ""}{total}
        </span>
        <span className="serif" style={{ fontSize: 15, marginTop: 4 }}>{intent}</span>
      </div>
    </div>
  );
}
