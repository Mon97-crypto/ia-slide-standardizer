/**
 * Header — IA logo, tab navigation, and the status pill.
 */
import { StatusPill, type Status } from "./StatusPill";

export type TabKey = "scan" | "ask" | "bulk";

const TABS: { key: TabKey; label: string }[] = [
  { key: "scan", label: "Scan" },
  { key: "ask", label: "Ask IAsense" },
  { key: "bulk", label: "Bulk upload" },
];

export function Header({
  tab,
  onTab,
  status,
  email,
}: {
  tab: TabKey;
  onTab: (t: TabKey) => void;
  status: Status;
  email?: string;
}) {
  return (
    <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 28, flexWrap: "wrap" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
        <img src="/ia_logo.png" alt="Impact Analytics" style={{ height: 34, width: "auto" }} />
        <nav role="tablist" style={{ display: "flex", gap: 4, background: "var(--ia-white)", padding: 4, borderRadius: 999, border: "1px solid var(--ia-gray-1)" }}>
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              data-active={tab === t.key}
              className="tab"
              onClick={() => onTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <StatusPill status={status} />
        {email && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="secondary" style={{ fontSize: 13 }}>{email}</span>
            <a href="/auth/logout" className="label" style={{ padding: "5px 11px", borderRadius: 999, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", textDecoration: "none", fontWeight: 600 }}>
              Sign out
            </a>
          </div>
        )}
      </div>
    </header>
  );
}
