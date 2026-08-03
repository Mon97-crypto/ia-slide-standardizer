/**
 * ResultsView — sleek dashboard: a score gauge + metric cards up top, then a
 * "Key signals" section and a "Supporting signals" section, each rendering its
 * signals in the catalog's defined order. Partial failures still render, with a
 * banner naming what was skipped.
 */
import type { ScanResult, ScoredSignal, StepKey } from "../lib/scan";
import type { AccountInfo } from "../lib/account";
import { KEY_SIGNALS, SUPPORTING_SIGNALS } from "../lib/scan-contract";
import { SignalRow } from "./SignalRow";
import { SignalSpectrum } from "./SignalSpectrum";
import { ScoreGauge } from "./ScoreGauge";
import { AccountCard } from "./AccountCard";

const STEP_NAMES: Record<StepKey, string> = {
  edgar: "SEC filings",
  techstack: "Tech stack",
  news: "News, hiring and Reddit",
};

export function ResultsView({
  result,
  onRefresh,
  account,
  accountLoading = false,
}: {
  result: ScanResult;
  onRefresh: () => void;
  account?: AccountInfo | null;
  accountLoading?: boolean;
}) {
  if (!result.verified) {
    return (
      <div className="card" style={{ padding: 20 }}>
        <p className="card-title" style={{ margin: 0 }}>We could not verify that company</p>
        <p className="secondary" style={{ marginTop: 8 }}>
          The website {result.domain} does not appear to belong to {result.company}. Check the spelling,
          or scan the company's real website.
        </p>
      </div>
    );
  }

  const byName = new Map(result.signals.map((s) => [s.name, s]));
  const keyRows = KEY_SIGNALS.map((id) => byName.get(id)).filter(Boolean) as ScoredSignal[];
  const supRows = SUPPORTING_SIGNALS.map((id) => byName.get(id)).filter(Boolean) as ScoredSignal[];
  const keyFound = keyRows.filter((s) => s.found).length;
  const supFound = supRows.filter((s) => s.found).length;
  const topOpp = result.signals
    .filter((s) => s.found && s.score_contribution > 0)
    .sort((a, b) => b.score_contribution - a.score_contribution)[0];

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Sticky context sub-header */}
      <div style={{ position: "sticky", top: 0, zIndex: 5, background: "var(--ia-offwhite)", paddingBlock: 8, display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, borderBottom: "1px solid var(--ia-gray-1)" }}>
        <div style={{ minWidth: 0 }}>
          <span className="card-title" style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{result.company}</span>
          <span className="secondary">{result.domain}</span>
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexShrink: 0 }}>
          <span className="tnum" style={{ fontSize: 20, fontWeight: 600, color: result.total < 0 ? "var(--ia-orange)" : "var(--ia-blue)" }}>
            {result.total > 0 ? "+" : ""}{result.total}
          </span>
          <span className="serif" style={{ fontSize: 16 }}>{result.intent}</span>
        </div>
      </div>

      {(account || accountLoading) && <AccountCard account={account ?? null} loading={accountLoading} />}

      {result.cached && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="label" style={{ padding: "3px 9px", borderRadius: 999, background: "var(--ia-white)", border: "1px solid var(--ia-gray-2)", color: "var(--ia-gray-3)" }}>
            cached{cachedAge(result)}
          </span>
          <button onClick={onRefresh} style={{ border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", borderRadius: 13, padding: "4px 12px", fontWeight: 500, fontSize: 14 }}>Refresh</button>
        </div>
      )}

      {result.failedSteps.length > 0 && (
        <div style={{ padding: "10px 14px", borderRadius: 13, border: "1px solid var(--ia-gray-2)", background: "var(--ia-white)", fontSize: 14 }}>
          {result.failedSteps.map((s) => STEP_NAMES[s]).join(" and ")} {result.failedSteps.length > 1 ? "were" : "was"} unavailable. Results below exclude {result.failedSteps.length > 1 ? "those sources" : "that source"}.
        </div>
      )}

      {/* Dashboard: gauge + metric cards */}
      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(220px, 260px) 1fr" }}>
        <div className="metric-card" style={{ padding: 20, display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <span className="eyebrow" style={{ marginBottom: 8 }}>Fit score</span>
          <ScoreGauge total={result.total} intent={result.intent} />
        </div>
        <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
          <Metric label="Key signals" value={`${keyFound}/${keyRows.length}`} />
          <Metric label="Supporting" value={`${supFound}/${supRows.length}`} />
          <Metric label="Top opportunity" value={topOpp ? topOpp.label : "—"} small />
          <div className="card" style={{ padding: 16, gridColumn: "1 / -1" }}>
            <span className="eyebrow" style={{ display: "block", marginBottom: 10 }}>Signal spectrum</span>
            <SignalSpectrum signals={result.signals} total={result.total} intent={result.intent} />
          </div>
        </div>
      </div>

      <Section title="Key signals" caption={`${keyFound} of ${keyRows.length} detected`} rows={keyRows} />
      <Section title="Supporting signals" caption={`${supFound} of ${supRows.length} detected`} rows={supRows} />
    </div>
  );
}

function Metric({ label, value, small }: { label: string; value: string; small?: boolean }) {
  return (
    <div className="card" style={{ padding: 16, display: "flex", flexDirection: "column", justifyContent: "center", gap: 4 }}>
      <span className="eyebrow">{label}</span>
      <span className={small ? "card-title" : "tnum"} style={small ? { fontSize: 15, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } : { fontSize: 26, fontWeight: 600 }}>
        {value}
      </span>
    </div>
  );
}

function Section({ title, caption, rows }: { title: string; caption: string; rows: ScoredSignal[] }) {
  return (
    <div className="card" style={{ padding: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 14px 12px" }}>
        <span className="h2" style={{ fontSize: 20 }}>{title}</span>
        <span className="secondary tnum">{caption}</span>
      </div>
      <div>
        {rows.map((s, i) => (
          <SignalRow key={s.name} signal={s} index={i} />
        ))}
      </div>
    </div>
  );
}

function cachedAge(result: ScanResult): string {
  const anyR = result as unknown as { cachedAgeMs?: number };
  if (!anyR.cachedAgeMs) return "";
  const h = Math.round(anyR.cachedAgeMs / (60 * 60 * 1000));
  if (h < 1) return " · under 1h ago";
  if (h < 48) return ` · ${h}h ago`;
  return ` · ${Math.round(h / 24)}d ago`;
}
