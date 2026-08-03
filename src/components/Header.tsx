/**
 * Header — IA logo, tab navigation, and the status pill.
 */
import { StatusPill, type Status } from "./StatusPill";

export type TabKey = "scan" | "contacts" | "ask" | "bulk";

const TABS: { key: TabKey; label: string }[] = [
  { key: "scan", label: "Scan" },
  { key: "contacts", label: "Contacts" },
  { key: "ask", label: "Ask IAsense" },
  { key: "bulk", label: "Bulk upload" },
];

export function Header({
  tab,
  onTab,
  status,
}: {
  tab: TabKey;
  onTab: (t: TabKey) => void;
  status: Status;
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
      <StatusPill status={status} />
    </header>
  );
}
