/**
 * DecisionMakers — the retail-planning buyers for the scanned account, shown as a
 * section at the bottom of a scan. Collapsed by default: Apollo is only called when
 * the user clicks "Find decision makers on Apollo" (saves credits). Then it lists
 * first name, last name, designation and tier, with a CSV export. Resets when the
 * scanned account changes.
 */
import { useEffect, useRef, useState } from "react";
import { downloadCsv, toCsv } from "../lib/csv";

interface Contact {
  firstName: string;
  lastName: string;
  title: string;
  tier: 1 | 2 | 3;
  function: string;
}

const TIER_LABEL: Record<number, string> = { 1: "Tier 1", 2: "Tier 2", 3: "Tier 3" };

type State = "idle" | "loading" | "loaded" | "error";

export function DecisionMakers({ company, domain }: { company: string; domain: string }) {
  const [state, setState] = useState<State>("idle");
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = `${company}|${domain}`;
  const prevKey = useRef(key);

  useEffect(() => {
    if (prevKey.current !== key) {
      prevKey.current = key;
      setState("idle");
      setContacts(null);
      setError(null);
    }
  }, [key]);

  async function find() {
    if (!domain) return;
    setState("loading");
    setError(null);
    try {
      const res = await fetch("/api/public/apollo-contacts", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ company, domain }),
      });
      const data = (await res.json()) as { ok: boolean; contacts: Contact[]; error?: string };
      if (!data.ok) {
        setError(data.error || "Contact lookup failed.");
        setState("error");
      } else {
        setContacts(data.contacts);
        setState("loaded");
      }
    } catch (e) {
      setError((e as Error).message);
      setState("error");
    }
  }

  function exportCsv() {
    if (!contacts?.length) return;
    const csv = toCsv(
      ["First name", "Last name", "Designation", "Tier"],
      contacts.map((c) => [c.firstName, c.lastName, c.title, c.tier]),
    );
    downloadCsv(`${company || "contacts"}-decision-makers.csv`, csv);
  }

  const sorted = contacts ? [...contacts].sort((a, b) => a.tier - b.tier) : [];

  return (
    <div className="card" style={{ padding: "16px 16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <span className="h2" style={{ fontSize: 20 }}>Decision makers</span>
          <div className="secondary" style={{ fontSize: 13, marginTop: 2 }}>Retail-planning buyers at {company}, via Apollo.</div>
        </div>
        {state === "idle" && <button onClick={find} style={btnPrimary}>Find decision makers on Apollo</button>}
        {state === "loading" && <span className="secondary">Finding buyers…</span>}
        {state === "error" && <button onClick={find} style={btnGhost}>Try again</button>}
        {state === "loaded" && sorted.length > 0 && <button onClick={exportCsv} style={btnGhost}>Download CSV</button>}
      </div>

      {state === "error" && error && (
        <p className="secondary" style={{ margin: "12px 0 0", color: "var(--ia-orange)" }}>
          {error}
          {error.includes("APOLLO_API_KEY") ? " Set APOLLO_API_KEY on the server." : ""}
        </p>
      )}

      {state === "loaded" && sorted.length === 0 && (
        <p className="secondary" style={{ margin: "12px 0 0" }}>No retail-planning decision-makers found for this account.</p>
      )}

      {state === "loaded" && sorted.length > 0 && (
        <div style={{ marginTop: 14, border: "1px solid var(--ia-gray-1)", borderRadius: 13, overflow: "hidden" }}>
          <div style={{ display: "flex", padding: "10px 14px", background: "var(--ia-offwhite)", borderBottom: "1px solid var(--ia-gray-1)" }}>
            <span className="eyebrow" style={{ width: 140, flexShrink: 0 }}>First name</span>
            <span className="eyebrow" style={{ width: 140, flexShrink: 0 }}>Last name</span>
            <span className="eyebrow" style={{ flex: 1, minWidth: 0 }}>Designation</span>
            <span className="eyebrow" style={{ width: 70, flexShrink: 0, textAlign: "right" }}>Tier</span>
          </div>
          {sorted.map((c, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", padding: "10px 14px", borderTop: i === 0 ? "none" : "1px solid var(--ia-gray-1)" }}>
              <span style={{ width: 140, flexShrink: 0, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.firstName || "—"}</span>
              <span style={{ width: 140, flexShrink: 0, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.lastName || "—"}</span>
              <span className="secondary" style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title}</span>
              <span className="label" style={{ width: 70, flexShrink: 0, textAlign: "right", color: "var(--ia-blue-dark)" }}>{TIER_LABEL[c.tier]}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const btnPrimary: React.CSSProperties = { height: 40, padding: "0 18px", borderRadius: 999, border: "none", background: "var(--ia-blue)", color: "var(--ia-white)", fontWeight: 600, fontSize: 14 };
const btnGhost: React.CSSProperties = { height: 38, padding: "0 16px", borderRadius: 999, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 14 };
