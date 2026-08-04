/**
 * BulkView — analyse up to 30 accounts at once. Add them by pasting a list of
 * websites (one per line) or uploading a CSV. Shows a ranked summary table with
 * Key / Supporting / Total signal counts; each row expands (via a + button) into
 * the full compact detail. Export summaries to CSV.
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

const MAX = 30;
const CONCURRENCY = 3;

const keyFoundOf = (res: ScanResult) => res.signals.filter((s) => s.group === "key" && s.found).length;
const supFoundOf = (res: ScanResult) => res.signals.filter((s) => s.group === "supporting" && s.found).length;
const foundOf = (res: ScanResult) => res.signals.filter((s) => s.found).length;

export function BulkView() {
  const [rows, setRows] = useState<Row[]>([]);
  const [text, setText] = useState("");
  const [running, setRunning] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function buildRows(pairs: { company: string; site: string }[]) {
    const next: Row[] = [];
    for (const { company, site } of pairs) {
      const domain = normalizeDomain(site || company);
      if (!domain) continue;
      if (next.some((r) => r.domain === domain)) continue; // de-dupe
      next.push({ company: company || companyFromDomain(domain), domain, status: "queued" });
      if (next.length >= MAX) break;
    }
    setRows(next);
    setExpanded(null);
  }

  function loadFromText() {
    const pairs = text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [a, b] = line.split(",").map((s) => s.trim());
        return b ? { company: a, site: b } : { company: "", site: a };
      });
    buildRows(pairs);
  }

  function onFile(file: File) {
    const reader = new FileReader();
    reader.onload = () => {
      const parsed = parseCsv(String(reader.result || ""));
      const looksHeader = parsed[0]?.some((c) => /company|website|domain|name|url/i.test(c));
      const body = looksHeader ? parsed.slice(1) : parsed;
      buildRows(body.map((r) => ({ company: (r[0] || "").trim(), site: (r[1] || "").trim() })));
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
      ["Company", "Website", "Key signals", "Supporting signals", "Total signals"],
      done.map((r) => {
        const res = r.result!;
        return [r.company, r.domain, keyFoundOf(res), supFoundOf(res), foundOf(res)];
      }),
    );
    downloadCsv("bulk-scan.csv", csv);
  }

  const doneCount = rows.filter((r) => r.status === "done" || r.status === "failed").length;
  const ranked = rows.map((r, i) => ({ r, i })).sort((a, b) => (b.r.result ? foundOf(b.r.result) : -1) - (a.r.result ? foundOf(a.r.result) : -1));

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Bulk upload</div>
        <h1 className="h1" style={{ margin: 0 }}>Rank a <span className="accent">list</span> at once.</h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 620 }}>
          Paste up to {MAX} websites (one per line) or upload a CSV. Get a ranked summary, then expand any row for the
          full signal detail. Cached results make re-runs instant.
        </p>
      </div>

      <section className="card" style={{ padding: 20, marginBottom: 24, display: "grid", gap: 14 }}>
        <label style={{ display: "grid", gap: 6 }}>
          <span className="eyebrow">Paste websites — one per line</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            placeholder={"gap.com\ntarget.com\nwilliams-sonoma.com"}
            style={{ resize: "vertical", padding: "12px 14px", borderRadius: 13, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", fontSize: 14, fontFamily: "inherit", color: "var(--ia-black)", lineHeight: 1.6 }}
          />
        </label>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <button onClick={loadFromText} disabled={!text.trim()} style={btnGhost}>Load list</button>
          <span className="secondary">or</span>
          <input ref={fileRef} type="file" accept=".csv,text/csv" style={{ display: "none" }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
          <button onClick={() => fileRef.current?.click()} style={btnGhost}>Upload CSV</button>
          <div style={{ flex: 1 }} />
          <button onClick={runAll} disabled={running || rows.length === 0} style={btnStyle(running || rows.length === 0)}>
            {running ? `Analysing ${doneCount}/${rows.length}…` : `Run analysis${rows.length ? ` (${rows.length})` : ""}`}
          </button>
          {rows.some((r) => r.result) && <button onClick={exportCsv} style={btnGhost}>Download CSV</button>}
        </div>
        <span className="secondary" style={{ fontSize: 13 }}>One website per line (or <code>Company, Website</code>). CSV: two columns — Company, Website. Max {MAX}.</span>
      </section>

      {rows.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <div style={{ display: "flex", alignItems: "center", padding: "12px 16px", borderBottom: "1px solid var(--ia-gray-1)" }}>
            <span style={{ width: 28, flexShrink: 0 }} />
            <span className="eyebrow" style={{ flex: 1 }}>Company</span>
            <span className="eyebrow" style={{ width: 70, textAlign: "right" }}>Key</span>
            <span className="eyebrow" style={{ width: 90, textAlign: "right" }}>Supporting</span>
            <span className="eyebrow" style={{ width: 70, textAlign: "right" }}>Total</span>
          </div>
          {ranked.map(({ r, i }) => {
            const res = r.result;
            const open = expanded === i;
            return (
              <div key={i} style={{ borderTop: "1px solid var(--ia-gray-1)" }}>
                <div onClick={() => res && setExpanded(open ? null : i)} style={{ display: "flex", alignItems: "center", padding: "12px 16px", cursor: res ? "pointer" : "default", gap: 0 }}>
                  <span aria-hidden style={{ width: 28, flexShrink: 0 }}>
                    <span style={{ width: 20, height: 20, borderRadius: 999, border: "1px solid var(--ia-gray-1)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 15, lineHeight: 1, color: res ? "var(--ia-blue)" : "var(--ia-gray-3)", background: open ? "var(--ia-blue-soft)" : "var(--ia-white)" }}>
                      {open ? "−" : "+"}
                    </span>
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.company}</div>
                    <div className="secondary">{r.domain}</div>
                  </div>
                  <span className="tnum" style={{ width: 70, textAlign: "right", fontWeight: 600 }}>{res ? keyFoundOf(res) : statusDot(r.status)}</span>
                  <span className="tnum secondary" style={{ width: 90, textAlign: "right" }}>{res ? supFoundOf(res) : ""}</span>
                  <span className="tnum" style={{ width: 70, textAlign: "right", fontWeight: 600, color: "var(--ia-blue)" }}>{res ? `${foundOf(res)}/${res.signals.length}` : (r.error ? "failed" : "")}</span>
                </div>
                {open && res && <div style={{ padding: "0 16px 16px" }}><ResultsView result={res} onRefresh={() => {}} compact /></div>}
              </div>
            );
          })}
        </div>
      )}

      {rows.length === 0 && (
        <div style={{ textAlign: "center", padding: "48px 0", color: "var(--ia-gray-3)" }}>
          <p className="secondary">Paste websites above or upload a CSV to analyse a list of accounts.</p>
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
