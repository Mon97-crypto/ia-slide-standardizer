/**
 * SignalsFoundRing — replaces the fit-score gauge. Shows how many signals were
 * found out of the total, with the reference design's sweeping dial + score-pop.
 */
export function SignalsFoundRing({ found, total }: { found: number; total: number }) {
  const R = 58;
  const C = 2 * Math.PI * R;
  const frac = total > 0 ? Math.max(0.02, found / total) : 0.02;
  const offset = C * (1 - frac);
  return (
    <div style={{ position: "relative", height: 148, width: 148, flexShrink: 0 }}>
      <svg viewBox="0 0 148 148" style={{ height: "100%", width: "100%", transform: "rotate(-90deg)" }}>
        <circle cx="74" cy="74" r={R} fill="none" stroke="var(--ia-gray-1)" strokeWidth="12" />
        <circle
          cx="74"
          cy="74"
          r={R}
          fill="none"
          stroke="var(--ia-blue)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={C}
          style={{
            ["--dial-circumference" as string]: `${C}`,
            ["--dial-offset" as string]: `${offset}`,
            strokeDashoffset: offset,
            animation: "dial-sweep 900ms cubic-bezier(.22,.61,.36,1) both",
          }}
        />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span
          className="serif tnum"
          style={{ fontSize: 44, lineHeight: 1, color: "var(--ia-blue)", animation: "score-pop 520ms cubic-bezier(.22,.61,.36,1) both" }}
        >
          {found}
        </span>
        <span className="secondary" style={{ marginTop: 4, fontSize: 13 }}>of {total}</span>
      </div>
    </div>
  );
}
