/**
 * ResultsView — the signal spectrum carries the page; everything else stays
 * quiet. A sticky sub-header holds company, score and intent so context survives
 * scrolling a long signal list. Partial failures still render, with a banner
 * naming what was skipped.
 */
import type { ScanResult, StepKey } from "../lib/scan";
import { SignalRow } from "./SignalRow";
import { SignalSpectrum } from "./SignalSpectrum";

const STEP_NAMES: Record<StepKey, string> = {
  edgar: "SEC filings",
  techstack: "Tech stack",
  news: "News and hiring",
};

export function ResultsView({
  result,
  onRefresh,
}: {
  result: ScanResult;
  onRefresh: () => void;
}) {
  if (!result.verified) {
    return (
      <div className="card" style={cardStyle}>
        <p className="card-title" style={{ margin: 0 }}>
          We could not verify that company
        </p>
        <p className="secondary" style={{ marginTop: 8 }}>
          The website {result.domain} does not appear to belong to {result.company}. Check the
          spelling, or scan the company's real website.
        </p>
      </div>
    );
  }

  const found = result.signals.filter((s) => s.found);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Sticky context sub-header */}
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 5,
          background: "var(--ia-offwhite)",
          paddingTop: 8,
          paddingBottom: 8,
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 12,
          borderBottom: "1px solid var(--ia-gray-1)",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <span className="card-title" style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {result.company}
          </span>
          <span className="secondary">{result.domain}</span>
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexShrink: 0 }}>
          <span className="tnum" style={{ fontSize: 20, fontWeight: 600, color: "var(--ia-blue)" }}>
            {result.total > 0 ? "+" : ""}
            {result.total}
          </span>
          <span className="serif" style={{ fontSize: 16 }}>{result.intent}</span>
        </div>
      </div>

      {result.cached && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            className="label"
            style={{ padding: "3px 9px", borderRadius: 999, background: "var(--ia-white)", border: "1px solid var(--ia-gray-2)", color: "var(--ia-gray-3)" }}
          >
            cached{cachedAge(result)}
          </span>
          <button onClick={onRefresh} style={refreshStyle}>
            Refresh
          </button>
        </div>
      )}

      {result.failedSteps.length > 0 && (
        <div style={bannerStyle}>
          {result.failedSteps.map((s) => STEP_NAMES[s]).join(" and ")}{" "}
          {result.failedSteps.length > 1 ? "were" : "was"} unavailable. Results below exclude{" "}
          {result.failedSteps.length > 1 ? "those sources" : "that source"}.
        </div>
      )}

      <div className="card" style={cardStyle}>
        <SignalSpectrum signals={result.signals} total={result.total} intent={result.intent} />
      </div>

      <div className="card" style={{ ...cardStyle, padding: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 14px 12px" }}>
          <span className="eyebrow">Signals</span>
          <span className="secondary tnum">
            {found.length} of {result.signals.length} detected
          </span>
        </div>
        <div>
          {result.signals.map((s, i) => (
            <SignalRow key={s.name} signal={s} index={i} />
          ))}
        </div>
      </div>
    </div>
  );
}

function cachedAge(result: ScanResult): string {
  const anyR = result as unknown as { cachedAgeMs?: number };
  if (!anyR.cachedAgeMs) return "";
  const h = Math.round(anyR.cachedAgeMs / (60 * 60 * 1000));
  if (h < 1) return " · under 1h ago";
  return ` · ${h}h ago`;
}

const cardStyle: React.CSSProperties = {
  background: "var(--ia-white)",
  border: "1px solid var(--ia-gray-1)",
  borderRadius: 20,
  boxShadow: "0 2px 10px rgba(20,20,30,.05)",
  padding: 20,
};

const bannerStyle: React.CSSProperties = {
  padding: "10px 14px",
  borderRadius: 13,
  border: "1px solid var(--ia-gray-2)",
  background: "var(--ia-white)",
  color: "var(--ia-black)",
  fontSize: 14,
};

const refreshStyle: React.CSSProperties = {
  border: "1px solid var(--ia-gray-1)",
  background: "var(--ia-white)",
  color: "var(--ia-blue)",
  borderRadius: 13,
  padding: "4px 12px",
  fontWeight: 500,
  fontSize: 14,
};
