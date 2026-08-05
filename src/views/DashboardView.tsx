/**
 * DashboardView — "My Dashboard". A personalised landing:
 *   - "Welcome <Name>!" derived from the logged-in email.
 *   - Two sub-tabs:
 *       Account Scan — every account synced from the Salesforce Google Sheet.
 *       My Accounts  — only accounts whose Owner.Name or BD_Owner__r maps to the
 *                      logged-in user.
 * Each row can be scanned directly (jumps to the Scan tab, pre-filled).
 */
import { useEffect, useMemo, useState } from "react";
import {
  fetchAccounts,
  displayNameFromEmail,
  nameTokensFromEmail,
  isMine,
  formatRevenue,
  type SheetAccount,
} from "../lib/accounts-sheet";
import { normalizeDomain, companyFromDomain } from "../lib/normalize";

type Sub = "all" | "mine";

export function DashboardView({
  email,
  onScan,
}: {
  email?: string;
  onScan: (req: { company: string; domain: string }) => void;
}) {
  const [sub, setSub] = useState<Sub>("all");
  const [accounts, setAccounts] = useState<SheetAccount[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "unconfigured" | "error">("loading");
  const [error, setError] = useState<string>("");
  const [q, setQ] = useState("");

  const load = (refresh = false) => {
    setState("loading");
    fetchAccounts(refresh).then((r) => {
      if (!r.configured) { setState("unconfigured"); return; }
      if (!r.ok) { setError(r.error || "Could not load accounts."); setState("error"); return; }
      setAccounts(r.accounts);
      setState("ready");
    });
  };
  useEffect(() => { load(); }, []);

  const name = displayNameFromEmail(email);
  const tokens = useMemo(() => nameTokensFromEmail(email), [email]);
  const mine = useMemo(() => accounts.filter((a) => isMine(a, tokens)), [accounts, tokens]);

  const base = sub === "mine" ? mine : accounts;
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return base;
    return base.filter((a) =>
      [a.name, a.domain, a.owner, a.bdOwner, a.type, a.status].some((f) => f.toLowerCase().includes(needle)),
    );
  }, [base, q]);

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>My dashboard · account intelligence</div>
        <h1 className="h1" style={{ margin: 0 }}>Welcome <span className="accent">{name}</span>!</h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 620 }}>
          Your Salesforce accounts, synced live. Browse the full book or jump to just the accounts you own — then
          scan any of them in one click.
        </p>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 4, background: "var(--ia-white)", padding: 4, borderRadius: 999, border: "1px solid var(--ia-gray-1)" }}>
          <SubTab active={sub === "all"} onClick={() => setSub("all")}>
            Account Scan{state === "ready" ? ` · ${accounts.length}` : ""}
          </SubTab>
          <SubTab active={sub === "mine"} onClick={() => setSub("mine")}>
            My Accounts{state === "ready" ? ` · ${mine.length}` : ""}
          </SubTab>
        </div>
        <div style={{ flex: 1 }} />
        {state === "ready" && (
          <>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter…"
              style={{ height: 38, padding: "0 12px", borderRadius: 11, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", fontSize: 14, fontFamily: "inherit", color: "var(--ia-black)", width: 180 }}
            />
            <button onClick={() => load(true)} style={btnGhost}>Refresh</button>
          </>
        )}
      </div>

      {state === "loading" && (
        <div style={{ textAlign: "center", padding: "56px 0", color: "var(--ia-gray-3)" }}>
          <p className="secondary">Loading your accounts…</p>
        </div>
      )}

      {state === "unconfigured" && (
        <div className="card" style={{ padding: 20 }}>
          <strong>Google Sheet not connected yet.</strong>
          <p className="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
            Add <code>GOOGLE_SHEET_ID</code>, <code>GOOGLE_SA_EMAIL</code> and <code>GOOGLE_SA_PRIVATE_KEY</code> in
            Render, and share the sheet (Viewer) with the service-account email. Accounts will appear here automatically.
          </p>
        </div>
      )}

      {state === "error" && (
        <div className="card" style={{ padding: 20, border: "1px solid var(--ia-orange)" }}>
          <strong style={{ color: "var(--ia-orange)" }}>Couldn't load accounts.</strong>
          <p className="secondary" style={{ marginTop: 8, marginBottom: 12 }}>{error}</p>
          <button onClick={() => load(true)} style={btnGhost}>Try again</button>
        </div>
      )}

      {state === "ready" && (
        rows.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 0", color: "var(--ia-gray-3)" }}>
            <p className="secondary">
              {sub === "mine"
                ? `No accounts are mapped to ${name} yet. We match your name against the Owner and BD Owner columns.`
                : "No accounts match your filter."}
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
