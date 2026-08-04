/**
 * DecisionMakers — the retail-planning buyers for the scanned account, shown as a
 * section at the bottom of a scan (ported from the reference layout). Auto-fetches
 * Apollo contacts for the company/domain, groups by tier, and exports to CSV.
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

export function DecisionMakers({ company, domain }: { company: string; domain: string }) {
  const [loading, setLoading] = useState(false);
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = `${company}|${domain}`;
  const lastKey = useRef<string>("");

  useEffect(() => {
    if (!domain || key === lastKey.current) return;
    lastKey.current = key;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setContacts(null);
    fetch("/api/public/apollo-contacts", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ company, domain }),
    })
      .then((r) => r.json())
      .then((data: { ok: boolean; contacts: Contact[]; error?: string }) => {
        if (cancelled) return;
        if (!data.ok) setError(data.error || "Contact lookup failed.");
        else setContacts(data.contacts);
      })
      .catch((e) => !cancelled && setError((e as Error).message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [key, company, domain]);

  function exportCsv() {
    if (!contacts?.length) return;
    const csv = toCsv(
      ["Name", "Title", "Function", "Tier", "Email", "LinkedIn"],
      contacts.map((c) => [c.name, c.title, c.function, c.tier, c.email, c.linkedinUrl]),
    );
    downloadCsv(`${company || "contacts"}-contacts.csv`, csv);
  }

  const tiers = [1, 2, 3] as const;

  return (
    <div className="card" style={{ padding: "16px 16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <span className="h2" style={{ fontSize: 20 }}>Decision makers</span>
        {contacts && contacts.length > 0 && (
          <button onClick={exportCsv} className="label" style={{ border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", borderRadius: 999, padding: "6px 14px", fontWeight: 600 }}>
            Download CSV
          </button>
        )}
      </div>

      {loading && <p className="secondary" style={{ margin: 0 }}>Finding the retail-planning buyers…</p>}

      {error && (
        <p className="secondary" style={{ margin: 0, color: "var(--ia-orange)" }}>
          {error}
          {error.includes("APOLLO_API_KEY") ? " Set APOLLO_API_KEY on the server." : ""}
        </p>
      )}

      {contacts && contacts.length === 0 && !loading && (
        <p className="secondary" style={{ margin: 0 }}>No retail-planning decision-makers found for this account.</p>
      )}

      {contacts && contacts.length > 0 && (
        <div style={{ display: "grid", gap: 14 }}>
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
                      <span className="secondary" style={{ width: 200, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.email || "—"}</span>
                      {c.linkedinUrl ? <a href={c.linkedinUrl} target="_blank" rel="noreferrer" className="label" style={{ flexShrink: 0 }}>LinkedIn</a> : <span style={{ width: 54, flexShrink: 0 }} />}
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
