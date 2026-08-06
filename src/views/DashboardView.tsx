/**
 * DashboardView — "My Dashboard". A personalised landing:
 *   - "Welcome <Name>!" derived from the logged-in email.
 *   - Two sub-tabs, both filtered SERVER-SIDE (the full ~10k-row book is never
 *     shipped to the browser):
 *       My Top Accounts — only accounts whose Owner.Name or BD_Owner__r map to
 *                         the signed-in user.
 *       All Accounts    — only accounts flagged Tier_1__c = TRUE in the sheet.
 * Each row can be scanned directly (jumps to the Scan tab, pre-filled).
 */
import { useEffect, useMemo, useState } from "react";
import {
  fetchAccounts,
  displayNameFromEmail,
  formatRevenue,
  type AccountScope,
  type SheetAccount,
} from "../lib/accounts-sheet";
import { normalizeDomain, companyFromDomain } from "../lib/normalize";

type LoadState = "loading" | "ready" | "unconfigured" | "error";

interface ScopeData {
  state: LoadState;
  accounts: SheetAccount[];
  error?: string;
}

const EMPTY: ScopeData = { state: "loading", accounts: [] };

export function DashboardView({
  email,
  onScan,
}: {
  email?: string;
  onScan: (req: { company: string; domain: string }) => void;
}) {
  const [scope, setScope] = useState<AccountScope>("mine");
  const [data, setData] = useState<Record<AccountScope, ScopeData>>({ mine: { ...EMPTY }, tier1: { ...EMPTY } });
  const [q, setQ] = useState("");

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

  // Load the active scope on first view / when it changes (once each).
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

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>My dashboard · account intelligence</div>
        <h1 className="h1" style={{ margin: 0 }}>Welcome <span className="accent">{name}</span>!</h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 640 }}>
          Your book of accounts, synced live from Salesforce. Jump to the accounts you own, or browse the
          Tier 1 target list — then scan any of them in one click.
        </p>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 4, background: "var(--ia-white)", padding: 4, borderRadius: 999, border: "1px solid var(--ia-gray-1)" }}>
          <SubTab active={scope === "mine"} onClick={() => setScope("mine")}>My Top Accounts{countLabel("mine")}</SubTab>
          <SubTab active={scope === "tier1"} onClick={() => setScope("tier1")}>All Accounts{countLabel("tier1")}</SubTab>
        </div>
        <div style={{ flex: 1 }} />
        {cur.state === "ready" && (
          <>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter…"
              style={{ height: 38, padding: "0 12px", borderRadius: 11, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", fontSize: 14, fontFamily: "inherit", color: "var(--ia-black)", width: 180 }}
            />
            <button onClick={() => load(scope, true)} style={btnGhost}>Refresh</button>
          </>
        )}
      </div>

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
            Render, and share the sheet (Viewer) with the service-account email. Accounts will appear here automatically.
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
                ? `No accounts are mapped to ${name} yet. We match your name against the Owner and BD Owner columns — if you expect accounts here, check how your name is written in those cells.`
                : "No Tier 1 accounts found. Flag accounts with Tier_1__c = TRUE in the sheet to surface them here."}
            </p>
          </div>
        ) : (
          <AccountsTable rows={rows} onScan={onScan} />
        )
      )}
    </div>
  );
}

function AccountsTable({
  rows,
  onScan,
}: {
  rows: SheetAccount[];
  onScan: (req: { company: string; domain: string }) => void;
}) {
  return (
    <div className="card" style={{ padding: 0, overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14, minWidth: 820 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--ia-gray-1)" }}>
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
            return (
              <tr key={i} style={{ borderTop: "1px solid var(--ia-gray-1)" }} className="hover-lift">
                <td style={td}>
                  <div style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis" }}>{a.name || companyFromDomain(domain)}</div>
                  {domain && (
                    <a href={`https://${domain}`} target="_blank" rel="noreferrer" className="secondary" style={{ color: "var(--ia-blue)", textDecoration: "none" }}>{domain}</a>
                  )}
                </td>
                <td style={td}>{a.owner || "—"}</td>
                <td style={td}>{a.bdOwner || "—"}</td>
                <td style={td}>{a.type || "—"}</td>
                <td style={td}>{a.status ? <StatusChip value={a.status} /> : "—"}</td>
                <td style={{ ...td, textAlign: "right" }} className="tnum">{formatRevenue(a.revenue)}</td>
                <td style={{ ...td, textAlign: "right" }}>
                  <button
                    disabled={!domain}
                    onClick={() => onScan({ company: a.name || companyFromDomain(domain), domain })}
                    style={{ height: 34, padding: "0 14px", borderRadius: 10, border: "none", background: domain ? "var(--ia-blue)" : "var(--ia-blue-light)", color: "var(--ia-white)", fontWeight: 600, fontSize: 13, whiteSpace: "nowrap" }}
                  >
                    Scan
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
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
  return (
    <button className="tab" data-active={active} aria-selected={active} onClick={onClick}>
      {children}
    </button>
  );
}

const Th = ({ children, right }: { children: React.ReactNode; right?: boolean }) => (
  <th className="eyebrow" style={{ textAlign: right ? "right" : "left", padding: "12px 16px", fontWeight: 600, whiteSpace: "nowrap" }}>{children}</th>
);
const td: React.CSSProperties = { padding: "12px 16px", verticalAlign: "top", maxWidth: 260 };
const btnGhost: React.CSSProperties = { height: 38, padding: "0 16px", borderRadius: 11, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 14 };
