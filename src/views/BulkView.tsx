/**
 * BulkView — upload up to 100 companies (Company, Website) as CSV, analyse them
 * with bounded concurrency, show a ranked summary table, and expand any row for
 * the full detail. Export summaries to CSV.
 */
import { useRef, useState } from "react";
import { parseCsv, toCsv, downloadCsv } from "../lib/csv";
import { runScan, type ScanResult } from "../lib/scan";
import { ResultsView } from "../components/ResultsView";
import { normalizeDomain, companyFromDomain } from "../lib/normalize";

interface Row {
  company: string;
  domain: string;
  status: "queued" | "running" | "done" | "failed";
  result?: ScanResult;
  error?: string;
}

const MAX = 100;
const CONCURRENCY = 3;

export function BulkView() {
  const [rows, setRows] = useState<Row[]>([]);
  const [running, setRunning] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function onFile(file: File) {
    const reader = new FileReader();
    reader.onload = () => {
      const parsed = parseCsv(String(reader.result || ""));
      const looksHeader = parsed[0]?.some((c) => /company|website|domain|name|url/i.test(c));
      const body = looksHeader ? parsed.slice(1) : parsed;
      const next: Row[] = [];
      for (const r of body) {
        const company = (r[0] || "").trim();
        const site = (r[1] || "").trim();
        const domain = normalizeDomain(site || company);
        if (!domain) continue;
        next.push({ company: company || companyFromDomain(domain), domain, status: "queued" });
        if (next.length >= MAX) break;
      }
      setRows(next); setExpanded(null);
    };
    reader.readAsText(file);
  }

  async function runAll() {
    setRunning(true);
    const queue = rows.map((_, i) => i);
    const worker = async () => {
      for (;;) {
        const i = queue.shift();
        if (i === undefined) return;
        setRows((rs) => rs.map((r, j) => (j === i ? { ...r, status: "running" } : r)));
        try {
          const result = await runScan({ company: rows[i].company, domain: rows[i].domain });
          setRows((rs) => rs.map((r, j) => (j === i ? { ...r, status: "done", result } : r)));
        } catch (e) {
          setRows((rs) => rs.map((r, j) => (j === i ? { ...r, status: "failed", error: (e as Error).message } : r)));
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, rows.length) }, worker));
    setRunning(false);
  }

  function exportCsv() {
    const done = rows.filter((r) => r.result);
    const csv = toCsv(
      ["Company", "Website", "Score", "Intent", "Key signals found", "Top opportunity"],
      done.map((r) => {
        const res = r.result!;
        const key = res.signals.filter((s) => s.group === "key" && s.found).length;
        const top = res.signals.filter((s) => s.found && s.score_contribution > 0).sort((a, b) => b.score_contribution - a.score_contribution)[0];
        return [r.company, r.domain, res.total, res.intent, key, top?.label ?? ""];
      }),
    );
    downloadCsv("bulk-scan.csv", csv);
  }

  const doneCount = rows.filter((r) => r.status === "done" || r.status === "failed").length;
  const ranked = rows.map((r, i) => ({ r, i })).sort((a, b) => (b.r.result?.total ?? -999) - (a.r.result?.total ?? -999));

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Bulk upload</div>
        <h1 className="h1" style={{ margin: 0 }}>Rank a <span className="accent">list</span> at once.</h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 620 }}>
          Upload up to 100 companies as CSV (Company, Website). Get a ranked summary, then expand any row for the
          full signal detail. Cached results make re-runs instant.
        </p>
      </div>

      <section className="card" style={{ padding: 20, marginBottom: 24, display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <input ref={fileRef} type="file" accept=".csv,text/csv" style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
        <button onClick={() => fileRef.current?.click()} style={btnGhost}>Choose CSV</button>
        <button onClick={runAll} disabled={running || rows.length === 0} style={btnStyle(running || rows.length === 0)}>
          {running ? `Analysing ${doneCount}/${rows.length}…` : `Run analysis${rows.length ? ` (${rows.length})` : ""}`}
        </button>
        {rows.some((r) => r.result) && <button onClick={exportCsv} style={btnGhost}>Download CSV</button>}
        <span className="secondary">Format: two columns — Company, Website. Max {MAX}.</span>
      </section>

      {rows.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <div style={{ display: "flex", padding: "12px 16px", borderBottom: "1px solid var(--ia-gray-1)" }}>
            <span className="eyebrow" style={{ flex: 1 }}>Company</span>
            <span className="eyebrow" style={{ width: 70, textAlign: "right" }}>Score</span>
            <span className="eyebrow" style={{ width: 130, textAlign: "right" }}>Intent</span>
            <span className="eyebrow" style={{ width: 220, textAlign: "right" }}>Top opportunity</span>
          </div>
          {ranked.map(({ r, i }) => {
            const res = r.result;
            const top = res?.signals.filter((s) => s.found && s.score_contribution > 0).sort((a, b) => b.score_contribution - a.score_contribution)[0];
            const open = expanded === i;
            return (
              <div key={i} style={{ borderTop: "1px solid var(--ia-gray-1)" }}>
                <div onClick={() => res && setExpanded(open ? null : i)} style={{ display: "flex", alignItems: "center", padding: "12px 16px", cursor: res ? "pointer" : "default" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.company}</div>
                    <div className="secondary">{r.domain}</div>
                  </div>
                  <span className="tnum" style={{ width: 70, textAlign: "right", fontWeight: 600, color: (res?.total ?? 0) < 0 ? "var(--ia-orange)" : "var(--ia-blue)" }}>
                    {res ? `${res.total > 0 ? "+" : ""}${res.total}` : statusDot(r.status)}
                  </span>
                  <span className="secondary serif" style={{ width: 130, textAlign: "right" }}>{res?.intent ?? ""}</span>
                  <span className="secondary" style={{ width: 220, textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{top?.label ?? (r.error ? "failed" : "")}</span>
                </div>
                {open && res && <div style={{ padding: "0 16px 16px" }}><ResultsView result={res} onRefresh={() => {}} /></div>}
              </div>
            );
          })}
        </div>
      )}

      {rows.length === 0 && (
        <div style={{ textAlign: "center", padding: "48px 0", color: "var(--ia-gray-3)" }}>
          <p className="secondary">Upload a CSV to analyse a list of accounts.</p>
        </div>
      )}
    </div>
  );
}

function statusDot(s: Row["status"]): string {
  return s === "running" ? "…" : s === "queued" ? "·" : "—";
}
const btnStyle = (d: boolean): React.CSSProperties => ({ height: 42, padding: "0 20px", borderRadius: 13, border: "none", background: d ? "var(--ia-blue-light)" : "var(--ia-blue)", color: "var(--ia-white)", fontWeight: 600, fontSize: 15 });
const btnGhost: React.CSSProperties = { height: 42, padding: "0 18px", borderRadius: 13, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 15 };
