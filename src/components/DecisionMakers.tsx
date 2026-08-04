/**
 * DecisionMakers — the retail-planning buyers for the scanned account, shown as a
 * section at the bottom of a scan. Collapsed by default: Apollo is only called when
 * the user clicks "Find decision makers on Apollo" (saves credits). Then it lists
 * the contacts by tier with a CSV export. Resets when the scanned account changes.
 */
import { useEffect, useRef, useState } from "react";
import { downloadCsv, toCsv } from "../lib/csv";

interface Contact {
  name: string;
  title: string;
  email: string | null;
  linkedinUrl: string | null;
  tier: 1 | 2 | 3;
  function: string;
}

const TIER_LABEL: Record<number, string> = {
  1: "Tier 1 · economic buyers",
  2: "Tier 2 · functional owners",
  3: "Tier 3 · directors",
};

type State = "idle" | "loading" | "loaded" | "error";

export function DecisionMakers({ company, domain }: { company: string; domain: string }) {
  const [state, setState] = useState<State>("idle");
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = `${company}|${domain}`;
  const prevKey = useRef(key);

  // A new scan (different account) collapses this back to the button.
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
      ["Name", "Title", "Function", "Tier", "LinkedIn"],
      contacts.map((c) => [c.name, c.title, c.function, c.tier, c.linkedinUrl]),
    );
    downloadCsv(`${company || "contacts"}-contacts.csv`, csv);
  }

  const tiers = [1, 2, 3] as const;

  return (
    <div className="card" style={{ padding: "16px 16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <span className="h2" style={{ fontSize: 20 }}>Decision makers</span>
          <div className="secondary" style={{ fontSize: 13, marginTop: 2 }}>Retail-planning buyers at {company}, via Apollo.</div>
        </div>
        {state === "idle" && (
          <button onClick={find} style={btnPrimary}>Find decision makers on Apollo</button>
        )}
        {state === "loading" && <span className="secondary">Finding buyers…</span>}
        {state === "error" && <button onClick={find} style={btnGhost}>Try again</button>}
        {state === "loaded" && contacts && contacts.length > 0 && (
          <button onClick={exportCsv} style={btnGhost}>Download CSV</button>
        )}
      </div>

      {state === "error" && error && (
        <p className="secondary" style={{ margin: "12px 0 0", color: "var(--ia-orange)" }}>
          {error}
          {error.includes("APOLLO_API_KEY") ? " Set APOLLO_API_KEY on the server." : ""}
        </p>
      )}

      {state === "loaded" && contacts && contacts.length === 0 && (
        <p className="secondary" style={{ margin: "12px 0 0" }}>No retail-planning decision-makers found for this account.</p>
      )}

      {state === "loaded" && contacts && contacts.length > 0 && (
        <div style={{ display: "grid", gap: 14, marginTop: 14 }}>
          {tiers.map((t) => {
            const rows = contacts.filter((c) => c.tier === t);
            if (!rows.length) return null;
            return (
              <div key={t}>
                <div className="eyebrow" style={{ marginBottom: 8 }}>{TIER_LABEL[t]}</div>
                <div style={{ display: "grid", gap: 8 }}>
                  {rows.map((c, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", borderRadius: 13, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)" }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 500 }}>{c.name || "—"}</div>
                        <div className="secondary" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title}</div>
                      </div>
                      <span className="label" style={{ padding: "2px 8px", borderRadius: 999, background: "var(--ia-blue-soft)", color: "var(--ia-blue-dark)", flexShrink: 0 }}>{c.function}</span>
                      {c.linkedinUrl ? (
                        <a href={c.linkedinUrl} target="_blank" rel="noreferrer" className="label" style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: 4, padding: "5px 12px", borderRadius: 999, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, textDecoration: "none" }}>
                          LinkedIn ↗
                        </a>
                      ) : (
                        <span className="secondary" style={{ flexShrink: 0, fontSize: 12 }}>No LinkedIn</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const btnPrimary: React.CSSProperties = { height: 40, padding: "0 18px", borderRadius: 999, border: "none", background: "var(--ia-blue)", color: "var(--ia-white)", fontWeight: 600, fontSize: 14 };
const btnGhost: React.CSSProperties = { height: 38, padding: "0 16px", borderRadius: 999, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 14 };
