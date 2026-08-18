/**
 * ProgressCard — three step rows (SEC filings / Tech stack / News and hiring).
 * Each pulses while pending, shows a blue check plus "N found" on resolve, or an
 * amber "unavailable" on failure. Progress bar = settled / 3. No green anywhere.
 */
import type { StepKey, StepStatus } from "../lib/scan";

export interface StepState {
  key: StepKey;
  label: string;
  status: StepStatus;
  foundCount?: number;
}

export function ProgressCard({ steps }: { steps: StepState[] }) {
  const settled = steps.filter((s) => s.status !== "pending").length;
  const progress = steps.length ? settled / steps.length : 0;

  return (
    <div className="card" style={cardStyle}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span className="card-title">Scanning the account</span>
        <span className="tnum secondary">{settled}/{steps.length}</span>
      </div>

      <div style={{ height: 6, borderRadius: 999, background: "var(--ia-offwhite)", overflow: "hidden", marginBottom: 16 }}>
        <div
          style={{
            height: "100%",
            width: `${progress * 100}%`,
            background: "var(--ia-blue)",
            borderRadius: 999,
            transition: "width 180ms cubic-bezier(.22,.61,.36,1)",
          }}
        />
      </div>

      <div style={{ display: "grid", gap: 2 }}>
        {steps.map((s) => (
          <StepRow key={s.key} step={s} />
        ))}
      </div>
    </div>
  );
}

function StepRow({ step }: { step: StepState }) {
  const pending = step.status === "pending";
  const failed = step.status === "failed";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, minHeight: 40 }}>
      <span
        aria-hidden
        style={{
          width: 18,
          height: 18,
          borderRadius: 999,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 12,
          flexShrink: 0,
          color: failed ? "var(--ia-orange)" : "var(--ia-white)",
          background: pending
            ? "var(--ia-gray-2)"
            : failed
              ? "transparent"
              : "var(--ia-blue)",
          border: failed ? "1.5px solid var(--ia-orange)" : "none",
          animation: pending ? "pulse 1.2s ease-in-out infinite" : "none",
        }}
      >
        {pending ? "" : failed ? "!" : "✓"}
      </span>
      <span style={{ flex: 1 }}>{step.label}</span>
      <span className="secondary tnum">
        {pending
          ? "checking…"
          : failed
            ? "unavailable"
            : `${step.foundCount ?? 0} found`}
      </span>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: "var(--ia-white)",
  border: "1px solid var(--ia-gray-1)",
  borderRadius: 20,
  boxShadow: "0 2px 10px rgba(20,20,30,.05)",
  padding: 20,
};
