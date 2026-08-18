/**
 * Header — IA logo, tab navigation, and the status pill.
 */
import { StatusPill, type Status } from "./StatusPill";

export type TabKey = "dashboard" | "scan" | "ask" | "bulk" | "admin" | "guide";

const BASE_TABS: { key: TabKey; label: string }[] = [
  { key: "scan", label: "Scan" },
  { key: "dashboard", label: "My dashboard" },
  { key: "bulk", label: "Bulk upload" },
  { key: "ask", label: "Ask IAsense" },
  { key: "guide", label: "How to use" },
];

export function Header({
  tab,
  onTab,
  status,
  email,
  isAdmin,
}: {
  tab: TabKey;
  onTab: (t: TabKey) => void;
  status: Status;
  email?: string;
  isAdmin?: boolean;
}) {
  const TABS = isAdmin ? [...BASE_TABS, { key: "admin" as TabKey, label: "Admin" }] : BASE_TABS;
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
