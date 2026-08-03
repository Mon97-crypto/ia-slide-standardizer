/**
 * ContactsView — run an Apollo search for a company and get the retail-planning
 * CXOs who actually buy (tier 1/2/3), with CSV export.
 */
import { useEffect, useRef, useState } from "react";
import { normalizeDomain, companyFromDomain } from "../lib/normalize";
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

export function ContactsView() {
  const [website, setWebsite] = useState("");
  const [company, setCompany] = useState("");
  const [loading, setLoading] = useState(false);
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [companyLabel, setCompanyLabel] = useState("");
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);

  async function run() {
    const domain = normalizeDomain(website);
    if (!domain) { ref.current?.focus(); return; }
    const co = company.trim() || companyFromDomain(domain);
    setCompanyLabel(co); setLoading(true); setError(null); setContacts(null);
    try {
      const res = await fetch("/api/public/apollo-contacts", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ company: co, domain }),
      });
      const data = (await res.json()) as { ok: boolean; contacts: Contact[]; error?: string };
      if (!data.ok) setError(data.error || "Apollo lookup failed.");
      else setContacts(data.contacts);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function exportCsv() {
    if (!contacts?.length) return;
    const csv = toCsv(
      ["Name", "Title", "Function", "Tier", "Email", "LinkedIn"],
      contacts.map((c) => [c.name, c.title, c.function, c.tier, c.email, c.linkedinUrl]),
    );
    downloadCsv(`${companyLabel || "contacts"}-contacts.csv`, csv);
  }

  const tiers = [1, 2, 3] as const;

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Apollo · decision-makers</div>
        <h1 className="h1" style={{ margin: 0 }}>Reach the <span className="accent">right</span> people.</h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 620 }}>
          Pull the retail-planning economic buyers and functional champions for any account — ranked by tier,
          HR/legal/marketing filtered out. Export to CSV.
        </p>
      </div>

      <section className="card" style={{ padding: 20, marginBottom: 24 }}>
        <form onSubmit={(e) => { e.preventDefault(); run(); }} style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr auto", alignItems: "end" }}>
          <label style={{ display: "grid", gap: 6 }}>
            <span className="eyebrow">Website</span>
            <input ref={ref} value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="acme.com" style={inputStyle} />
          </label>
          <label style={{ display: "grid", gap: 6 }}>
            <span className="eyebrow">Company (optional)</span>
            <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme Retail" style={inputStyle} />
          </label>
          <button type="submit" disabled={loading} style={btnStyle(loading)}>{loading ? "Searching…" : "Find contacts"}</button>
        </form>
      </section>

      {error && (
        <div style={{ padding: "12px 16px", borderRadius: 13, border: "1px solid var(--ia-orange)", background: "var(--ia-white)", marginBottom: 20 }}>
          <strong style={{ color: "var(--ia-orange)" }}>Couldn't load contacts.</strong> {error}
          {error.includes("APOLLO_API_KEY") && <span> Set <code>APOLLO_API_KEY</code> on the server.</span>}
        </div>
      )}

      {contacts && (
        <div style={{ display: "grid", gap: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span className="secondary tnum">{contacts.length} contacts for {companyLabel}</span>
            <button onClick={exportCsv} disabled={!contacts.length} style={btnStyle(false)}>Download CSV</button>
          </div>
          {contacts.length === 0 && <div className="card" style={{ padding: 20 }}><span className="secondary">No matching decision-makers found.</span></div>}
          {tiers.map((t) => {
            const rows = contacts.filter((c) => c.tier === t);
            if (!rows.length) return null;
            return (
              <div key={t} className="card" style={{ padding: 0 }}>
                <div style={{ padding: "14px 16px 10px" }}><span className="eyebrow">{TIER_LABEL[t]}</span></div>
                {rows.map((c, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", borderTop: "1px solid var(--ia-gray-1)" }}>
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
            );
          })}
        </div>
      )}

      {!contacts && !error && !loading && (
        <div style={{ textAlign: "center", padding: "48px 0", color: "var(--ia-gray-3)" }}>
          <p className="secondary">Enter a company website to pull its decision-makers.</p>
        </div>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = { height: 44, padding: "0 14px", borderRadius: 13, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", fontSize: 15, fontFamily: "inherit", color: "var(--ia-black)" };
function btnStyle(disabled: boolean): React.CSSProperties {
  return { height: 44, padding: "0 20px", borderRadius: 13, border: "none", background: disabled ? "var(--ia-blue-light)" : "var(--ia-blue)", color: "var(--ia-white)", fontWeight: 600, fontSize: 15 };
}
