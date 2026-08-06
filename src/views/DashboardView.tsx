/**
 * DashboardView — "My Dashboard". A personalised landing:
 *   - "Welcome <Name>!" derived from the logged-in email.
 *   - Two sub-tabs, filtered SERVER-SIDE (the full book never reaches the browser):
 *       My Top Accounts — accounts whose Owner.Name / BD_Owner__r map to the user.
 *       All Accounts    — accounts flagged Tier_1__c = TRUE.
 *   - Scan any account INLINE (results open as a dropdown under the row), or select
 *     up to 10 with the "+" button and scan them in one go.
 */
import { useEffect, useMemo, useState } from "react";
import {
  fetchAccounts,
  displayNameFromEmail,
  formatRevenue,
  type AccountScope,
  type SheetAccount,
} from "../lib/accounts-sheet";
import { runScan, type ScanResult } from "../lib/scan";
import { ResultsView } from "../components/ResultsView";
import { normalizeDomain, companyFromDomain } from "../lib/normalize";

type LoadState = "loading" | "ready" | "unconfigured" | "error";
const MAX_SELECT = 10;
const SCAN_CONCURRENCY = 3;

interface ScopeData {
  state: LoadState;
  accounts: SheetAccount[];
  error?: string;
}
interface RowScan {
  status: "running" | "done" | "failed";
  result?: ScanResult;
  error?: string;
}

const EMPTY: ScopeData = { state: "loading", accounts: [] };

export function DashboardView({ email }: { email?: string }) {
  const [scope, setScope] = useState<AccountScope>("mine");
  const [data, setData] = useState<Record<AccountScope, ScopeData>>({ mine: { ...EMPTY }, tier1: { ...EMPTY } });
  const [q, setQ] = useState("");
  const [scans, setScans] = useState<Record<string, RowScan>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const load = (s: AccountScope, refresh = false) => {
    setData((d) => ({ ...d, [s]: { ...EMPTY, state: "loading" } }));
    fetchAccounts(s, refresh).then((r) => {
      setData((d) => ({
        ...d,
        [s]: r.configured === false
          ? { state: "unconfigured", accounts: [] }
          : !r.ok
          ? { state: "error", accounts: [], error: r.error || "Could not load accounts." }
          : { state: "ready", accounts: r.accounts },
      }));
    });
  };

  useEffect(() => {
    if (data[scope].state === "loading" && data[scope].accounts.length === 0) load(scope);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope]);

  const name = displayNameFromEmail(email);
  const cur = data[scope];

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return cur.accounts;
    return cur.accounts.filter((a) =>
      [a.name, a.domain, a.owner, a.bdOwner, a.type, a.status].some((f) => (f || "").toLowerCase().includes(needle)),
    );
  }, [cur.accounts, q]);

  const countLabel = (s: AccountScope) => (data[s].state === "ready" ? ` · ${data[s].accounts.length}` : "");

  // ---- scanning ----
  async function scanOne(company: string, domain: string, refresh = false) {
    if (!domain) return;
    setScans((m) => ({ ...m, [domain]: { status: "running" } }));
    setExpanded((e) => new Set(e).add(domain));
    try {
      const result = await runScan({ company, domain, refresh });
      setScans((m) => ({ ...m, [domain]: { status: "done", result } }));
    } catch (e) {
      setScans((m) => ({ ...m, [domain]: { status: "failed", error: (e as Error).message } }));
    }
  }

  async function scanSelected() {
    const picked = rows
      .map((a) => ({ company: a.name || companyFromDomain(normalizeDomain(a.domain)), domain: normalizeDomain(a.domain) }))
      .filter((r) => r.domain && selected.has(r.domain));
    if (!picked.length) return;
    const queue = [...picked];
    const worker = async () => {
      for (;;) {
        const next = queue.shift();
        if (!next) return;
        await scanOne(next.company, next.domain);
      }
    };
    await Promise.all(Array.from({ length: Math.min(SCAN_CONCURRENCY, picked.length) }, worker));
  }

  function toggleSelect(domain: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(domain)) next.delete(domain);
      else if (next.size < MAX_SELECT) next.add(domain);
      return next;
    });
  }
  function toggleExpand(domain: string) {
    setExpanded((e) => {
      const next = new Set(e);
      if (next.has(domain)) next.delete(domain);
      else next.add(domain);
      return next;
    });
  }

  const anyScanning = Object.values(scans).some((s) => s.status === "running");

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>My dashboard · account intelligence</div>
        <h1 className="h1" style={{ margin: 0 }}>Welcome <span className="accent">{name}</span>!</h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 640 }}>
          Your book of accounts, synced live from Salesforce. Scan any account right here, or pick up to {MAX_SELECT}
          {" "}with the <strong>+</strong> button and scan them together.
        </p>
      </div>

      {/* Toolbar: sub-tabs + refresh (left) · filter + notifications (right) */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 4, background: "var(--ia-white)", padding: 4, borderRadius: 999, border: "1px solid var(--ia-gray-1)" }}>
          <SubTab active={scope === "mine"} onClick={() => setScope("mine")}>My Top Accounts{countLabel("mine")}</SubTab>
          <SubTab active={scope === "tier1"} onClick={() => setScope("tier1")}>All Accounts{countLabel("tier1")}</SubTab>
        </div>
        {cur.state === "ready" && (
          <button onClick={() => load(scope, true)} title="Refresh accounts" aria-label="Refresh accounts" style={iconBtn}>
            <RefreshIcon />
          </button>
        )}
        <div style={{ flex: 1 }} />
        {cur.state === "ready" && (
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter…"
            style={{ height: 38, padding: "0 12px", borderRadius: 11, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", fontSize: 14, fontFamily: "inherit", color: "var(--ia-black)", width: 180 }}
          />
        )}
        <button title="Notifications" aria-label="Notifications" style={iconBtn}>
          <BellIcon />
        </button>
      </div>

      {/* Selection action bar */}
      {selected.size > 0 && (
        <div className="anim-fade-up" style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14, padding: "10px 14px", borderRadius: 13, background: "var(--ia-blue-soft)", border: "1px solid var(--ia-blue-soft)" }}>
          <span style={{ fontWeight: 600, color: "var(--ia-blue-dark)", fontSize: 14 }}>
            {selected.size} selected <span className="secondary" style={{ fontWeight: 400 }}>· max {MAX_SELECT}</span>
          </span>
          <div style={{ flex: 1 }} />
          <button onClick={() => setSelected(new Set())} style={btnGhost}>Clear</button>
          <button onClick={scanSelected} disabled={anyScanning} style={btnPrimary(anyScanning)}>
            {anyScanning ? "Scanning…" : `Scan ${selected.size} selected`}
          </button>
        </div>
      )}

      {cur.state === "loading" && (
        <div style={{ textAlign: "center", padding: "56px 0", color: "var(--ia-gray-3)" }}>
          <p className="secondary">Loading accounts…</p>
        </div>
      )}

      {cur.state === "unconfigured" && (
        <div className="card" style={{ padding: 20 }}>
          <strong>Google Sheet not connected yet.</strong>
          <p className="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
            Add <code>GOOGLE_SHEET_ID</code>, <code>GOOGLE_SA_EMAIL</code> and <code>GOOGLE_SA_PRIVATE_KEY</code> in
            Render, and share the sheet (Viewer) with the service-account email.
          </p>
        </div>
      )}

      {cur.state === "error" && (
        <div className="card" style={{ padding: 20, border: "1px solid var(--ia-orange)" }}>
          <strong style={{ color: "var(--ia-orange)" }}>Couldn't load accounts.</strong>
          <p className="secondary" style={{ marginTop: 8, marginBottom: 12 }}>{cur.error}</p>
          <button onClick={() => load(scope, true)} style={btnGhost}>Try again</button>
        </div>
      )}

      {cur.state === "ready" && (
        rows.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 0", color: "var(--ia-gray-3)" }}>
            <p className="secondary">
              {q.trim()
                ? "No accounts match your filter."
                : scope === "mine"
                ? `No accounts are mapped to ${name} yet. We match your name against the Owner and BD Owner columns.`
                : "No Tier 1 accounts found. Flag accounts with Tier_1__c = TRUE in the sheet to surface them here."}
            </p>
          </div>
        ) : (
          <AccountsTable
            rows={rows}
            scans={scans}
            expanded={expanded}
            selected={selected}
            atMax={selected.size >= MAX_SELECT}
            onSelect={toggleSelect}
            onExpand={toggleExpand}
            onScan={scanOne}
          />
        )
      )}
    </div>
  );
}

function AccountsTable({
  rows, scans, expanded, selected, atMax, onSelect, onExpand, onScan,
}: {
  rows: SheetAccount[];
  scans: Record<string, RowScan>;
  expanded: Set<string>;
  selected: Set<string>;
  atMax: boolean;
  onSelect: (domain: string) => void;
  onExpand: (domain: string) => void;
  onScan: (company: string, domain: string, refresh?: boolean) => void;
}) {
  return (
    <div className="card" style={{ padding: 0, overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14, minWidth: 860 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--ia-gray-1)" }}>
            <Th> </Th>
            <Th>Account</Th>
            <Th>Owner</Th>
            <Th>BD Owner</Th>
            <Th>Type</Th>
            <Th>Status</Th>
            <Th right>Annual revenue</Th>
            <Th right> </Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a, i) => {
            const domain = normalizeDomain(a.domain);
            const company = a.name || companyFromDomain(domain);
            const scan = scans[domain];
            const isOpen = expanded.has(domain);
            const isSel = selected.has(domain);
            return (
              <FragmentRow key={i}>
                <tr style={{ borderTop: "1px solid var(--ia-gray-1)" }}>
                  <td style={{ ...td, width: 42 }}>
                    <button
                      onClick={() => domain && onSelect(domain)}
                      disabled={!domain || (atMax && !isSel)}
                      title={isSel ? "Deselect" : atMax ? `Max ${MAX_SELECT} selected` : "Select to batch-scan"}
                      aria-label={isSel ? "Deselect" : "Select"}
                      style={{
                        width: 24, height: 24, borderRadius: 7, display: "inline-flex", alignItems: "center", justifyContent: "center",
                        border: isSel ? "none" : "1px solid var(--ia-gray-1)", cursor: !domain || (atMax && !isSel) ? "default" : "pointer",
                        background: isSel ? "var(--ia-blue)" : "var(--ia-white)", color: isSel ? "#fff" : "var(--ia-gray-3)",
                        fontSize: 15, lineHeight: 1, opacity: !domain || (atMax && !isSel) ? 0.4 : 1,
                      }}
                    >
                      {isSel ? "✓" : "+"}
                    </button>
                  </td>
                  <td style={td}>
                    <div style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis" }}>{company}</div>
                    {domain && <a href={`https://${domain}`} target="_blank" rel="noreferrer" className="secondary" style={{ color: "var(--ia-blue)", textDecoration: "none" }}>{domain}</a>}
                  </td>
                  <td style={td}>{a.owner || "—"}</td>
                  <td style={td}>{a.bdOwner || "—"}</td>
                  <td style={td}>{a.type || "—"}</td>
                  <td style={td}>{a.status ? <StatusChip value={a.status} /> : "—"}</td>
                  <td style={{ ...td, textAlign: "right" }} className="tnum">{formatRevenue(a.revenue)}</td>
                  <td style={{ ...td, textAlign: "right", whiteSpace: "nowrap" }}>
                    {!scan && (
                      <button disabled={!domain} onClick={() => onScan(company, domain)} style={scanBtn(!domain)}>Scan</button>
                    )}
                    {scan?.status === "running" && <span className="secondary" style={{ fontSize: 13 }}>Scanning…</span>}
                    {scan?.status === "done" && (
                      <button onClick={() => onExpand(domain)} style={viewBtn}>{isOpen ? "Hide" : "View"}</button>
                    )}
                    {scan?.status === "failed" && (
                      <button onClick={() => onScan(company, domain, true)} style={{ ...viewBtn, color: "var(--ia-orange)", borderColor: "var(--ia-orange)" }}>Retry</button>
                    )}
                  </td>
                </tr>
                {isOpen && scan?.status === "done" && scan.result && (
                  <tr>
                    <td colSpan={8} style={{ padding: "0 16px 18px", background: "var(--ia-offwhite)" }}>
                      <div style={{ paddingTop: 12 }}>
                        <ResultsView result={scan.result} compact onRefresh={() => onScan(company, domain, true)} />
                      </div>
                    </td>
                  </tr>
                )}
                {isOpen && scan?.status === "failed" && (
                  <tr>
                    <td colSpan={8} style={{ padding: "0 16px 16px" }}>
                      <div style={{ color: "var(--ia-orange)", fontSize: 14 }}>Scan failed: {scan.error}</div>
                    </td>
                  </tr>
                )}
              </FragmentRow>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

function StatusChip({ value }: { value: string }) {
  const v = value.toLowerCase();
  const positive = /(active|customer|won|closed won|existing)/.test(v);
  const warm = /(prospect|open|target|pipeline|lead|negoti)/.test(v);
  const bg = positive ? "var(--ia-blue-soft)" : warm ? "#fff1e8" : "var(--ia-gray-1)";
  const color = positive ? "var(--ia-blue-dark)" : warm ? "var(--ia-orange)" : "var(--ia-gray-3)";
  return <span className="label" style={{ padding: "3px 9px", borderRadius: 999, background: bg, color }}>{value}</span>;
}

function SubTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button className="tab" data-active={active} aria-selected={active} onClick={onClick}>{children}</button>;
}

function RefreshIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 3v6h-6" />
    </svg>
  );
}
function BellIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

const Th = ({ children, right }: { children: React.ReactNode; right?: boolean }) => (
  <th className="eyebrow" style={{ textAlign: right ? "right" : "left", padding: "12px 16px", fontWeight: 600, whiteSpace: "nowrap" }}>{children}</th>
);
const td: React.CSSProperties = { padding: "12px 16px", verticalAlign: "top", maxWidth: 260 };
const iconBtn: React.CSSProperties = { width: 38, height: 38, borderRadius: 11, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", display: "inline-flex", alignItems: "center", justifyContent: "center", cursor: "pointer" };
const btnGhost: React.CSSProperties = { height: 36, padding: "0 14px", borderRadius: 11, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 14 };
const btnPrimary = (d: boolean): React.CSSProperties => ({ height: 36, padding: "0 16px", borderRadius: 11, border: "none", background: d ? "var(--ia-blue-light)" : "var(--ia-blue)", color: "#fff", fontWeight: 600, fontSize: 14 });
const scanBtn = (d: boolean): React.CSSProperties => ({ height: 34, padding: "0 16px", borderRadius: 10, border: "none", background: d ? "var(--ia-blue-light)" : "var(--ia-blue)", color: "#fff", fontWeight: 600, fontSize: 13 });
const viewBtn: React.CSSProperties = { height: 34, padding: "0 16px", borderRadius: 10, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 13 };
