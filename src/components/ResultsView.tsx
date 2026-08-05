/**
 * ResultsView — sleek dashboard: a score gauge + metric cards up top, then a
 * "Key signals" section and a "Supporting signals" section, each rendering its
 * signals in the catalog's defined order. Partial failures still render, with a
 * banner naming what was skipped.
 */
import type { ScanResult, ScoredSignal, StepKey } from "../lib/scan";
import type { AccountInfo } from "../lib/account";
import { KEY_SIGNALS, SUPPORTING_SIGNALS } from "../lib/scan-contract";
import { SignalTile } from "./SignalTile";
import { SignalsFoundRing } from "./SignalsFoundRing";
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
  compact = false,
}: {
  result: ScanResult;
  onRefresh: () => void;
  account?: AccountInfo | null;
  accountLoading?: boolean;
  /** Hide the sticky company sub-header (e.g. inside a bulk row that already shows it). */
  compact?: boolean;
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
  const totalCatalog = keyRows.length + supRows.length;
  const totalFound = keyFound + supFound;
  const positiveCount = result.signals.filter((s) => s.found && s.type === "positive").length;
  const negativeCount = result.signals.filter((s) => s.found && s.type === "negative").length;
  const mixedCount = result.signals.filter((s) => s.found && s.type === "neutral").length;
  const topOpp = result.signals
    .filter((s) => s.found && s.score_contribution > 0)
    .sort((a, b) => b.score_contribution - a.score_contribution)[0];

  return (
    <div className="anim-fade-up" style={{ display: "grid", gap: 16 }}>
      {/* Sticky context sub-header (hidden in compact/bulk mode) */}
      {!compact && (
        <div style={{ position: "sticky", top: 0, zIndex: 5, background: "var(--ia-offwhite)", paddingBlock: 8, display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, borderBottom: "1px solid var(--ia-gray-1)" }}>
          <div style={{ minWidth: 0 }}>
            <span className="card-title" style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{result.company}</span>
            <span className="secondary">{result.domain}</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexShrink: 0 }}>
            <span className="tnum" style={{ fontSize: 20, fontWeight: 600, color: "var(--ia-blue)" }}>
              {totalFound}/{totalCatalog}
            </span>
            <span className="secondary">signals</span>
          </div>
        </div>
      )}

      {(account || accountLoading) && <AccountCard account={account ?? null} loading={accountLoading} />}

      {(result.newsClassifier || result.resolvedEntity) && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, fontSize: 12 }}>
          {result.resolvedEntity && (
            <span className="label" style={{ padding: "3px 9px", borderRadius: 999, background: "var(--ia-blue-soft)", color: "var(--ia-blue-dark)" }}>
              News matched to: {result.resolvedEntity}
            </span>
          )}
          {result.newsClassifier && (
            <span className="label" style={{ padding: "3px 9px", borderRadius: 999,
              background: result.newsClassifier === "llm-grounded" ? "var(--ia-blue-soft)" : "#fff1e8",
              color: result.newsClassifier === "llm-grounded" ? "var(--ia-blue-dark)" : "var(--ia-orange)" }}>
              {result.newsClassifier === "llm-grounded"
                ? "AI-verified news (entity + recency checked)"
                : result.newsClassifier === "none"
                ? "No recent news found in the last 365 days"
                : "Keyword-matched news — set ANTHROPIC_API_KEY for AI entity filtering"}
            </span>
          )}
        </div>
      )}

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

      {/* Dashboard: signals-found ring + metric cards */}
      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(220px, 260px) 1fr" }}>
        <div className="metric-card" style={{ padding: 20, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10 }}>
          <span className="eyebrow" style={{ alignSelf: "flex-start" }}>Signals found</span>
          <SignalsFoundRing found={totalFound} total={totalCatalog} />
        </div>
        <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
          <Metric label="Key signals" value={`${keyFound}/${keyRows.length}`} />
          <Metric label="Supporting" value={`${supFound}/${supRows.length}`} />
          <Metric label="Top signal" value={topOpp ? topOpp.label : "—"} small />
          <div className="card" style={{ padding: 16, gridColumn: "1 / -1", display: "flex", flexDirection: "column", gap: 10 }}>
            <span className="eyebrow">Signals detected</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              <Chip label={`${keyFound} key`} tone="blue" />
              <Chip label={`${supFound} supporting`} tone="muted" />
              <Chip label={`${positiveCount} positive`} tone="blue" />
              <Chip label={`${negativeCount} negative`} tone="risk" />
              <Chip label={`${mixedCount} mixed`} tone="muted" />
            </div>
          </div>
        </div>
      </div>

      <Section title="Key signals" caption={`${keyFound} of ${keyRows.length} detected`} rows={keyRows.filter((r) => r.found)} emptyText="No key signals detected in this window." />
      <Section title="Supporting signals" caption={`${supFound} of ${supRows.length} detected`} rows={supRows.filter((r) => r.found)} emptyText="No supporting signals detected in this window." />
      <Undetected rows={[...keyRows, ...supRows].filter((r) => !r.found)} />
    </div>
  );
}

function Undetected({ rows }: { rows: ScoredSignal[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="card" style={{ padding: "16px 16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <span className="eyebrow" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span aria-hidden style={{ color: "var(--ia-gray-2)" }}>○</span>
          No detected signals · {rows.length}
        </span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {rows.map((r) => (
          <span key={r.name} className="label" style={{ display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 999, border: "1px solid var(--ia-gray-1)", background: "var(--ia-offwhite)", padding: "5px 11px", fontSize: 13, color: "var(--ia-gray-3)" }}>
            <span aria-hidden style={{ color: "var(--ia-gray-2)" }}>{r.glyph}</span>
            {r.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function Chip({ label, tone }: { label: string; tone: "blue" | "risk" | "muted" }) {
  const color = tone === "risk" ? "var(--ia-orange)" : tone === "muted" ? "var(--ia-gray-3)" : "var(--ia-blue)";
  const bg = tone === "risk" ? "#fff1e8" : tone === "muted" ? "var(--ia-offwhite)" : "var(--ia-blue-soft)";
  return (
    <span className="label" style={{ padding: "5px 12px", borderRadius: 999, background: bg, color, fontSize: 13, fontWeight: 500 }}>
      {label}
    </span>
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

function Section({ title, caption, rows, emptyText }: { title: string; caption: string; rows: ScoredSignal[]; emptyText: string }) {
  return (
    <div className="card" style={{ padding: "16px 16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span className="h2" style={{ fontSize: 20 }}>{title}</span>
        <span className="secondary tnum">{caption}</span>
      </div>
      {rows.length > 0 ? (
        <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 340px), 1fr))" }}>
          {rows.map((s, i) => (
            <SignalTile key={s.name} signal={s} index={i} />
          ))}
        </div>
      ) : (
        <p className="secondary" style={{ margin: 0 }}>{emptyText}</p>
      )}
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
