/**
 * CrmCard — shown under the Account Information when the scanned website exists in
 * the Salesforce Google Sheet. Surfaces the CRM context for the account: Account
 * Owner, BD Owner, Type and Status. If the logged-in user owns the account (their
 * name maps to Owner.Name or BD_Owner__r), it's highlighted as "Owned by you".
 */
import { useEffect, useState } from "react";
import {
  findAccountByDomain,
  nameTokensFromEmail,
  ownerMatches,
  displayNameFromEmail,
  type SheetAccount,
} from "../lib/accounts-sheet";

export function CrmCard({ domain, email }: { domain: string; email?: string }) {
  const [account, setAccount] = useState<SheetAccount | null>(null);
  const [state, setState] = useState<"loading" | "done">("loading");

  useEffect(() => {
    let alive = true;
    setState("loading");
    setAccount(null);
    findAccountByDomain(domain)
      .then((a) => { if (alive) { setAccount(a); setState("done"); } })
      .catch(() => { if (alive) setState("done"); });
    return () => { alive = false; };
  }, [domain]);

  // Nothing to show if the account isn't in the sheet (or sheet isn't connected).
  if (state === "loading" || !account) return null;

  const tokens = nameTokensFromEmail(email);
  const ownerIsMe = ownerMatches(account.owner, tokens);
  const bdIsMe = ownerMatches(account.bdOwner, tokens);
  const mine = ownerIsMe || bdIsMe;
  const you = displayNameFromEmail(email);

  return (
    <div className="card anim-fade-up" style={{ padding: 0, overflow: "hidden" }}>
      {/* Gradient header strip */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, padding: "13px 18px",
        background: mine
          ? "linear-gradient(90deg, var(--ia-blue) 0%, var(--ia-blue-dark) 100%)"
          : "linear-gradient(90deg, var(--ia-blue-soft) 0%, rgba(37,99,235,0.06) 100%)",
      }}>
        <SalesforceGlyph color={mine ? "#fff" : "var(--ia-blue)"} />
        <span className="eyebrow" style={{ color: mine ? "rgba(255,255,255,0.85)" : "var(--ia-blue-dark)", letterSpacing: "0.08em" }}>
          Salesforce account
        </span>
        <div style={{ flex: 1 }} />
        {mine ? (
          <span className="label" style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 11px", borderRadius: 999, background: "rgba(255,255,255,0.2)", color: "#fff", fontWeight: 600, fontSize: 12 }}>
            <span aria-hidden>★</span> Owned by you
          </span>
        ) : (
          <span className="label" style={{ padding: "4px 11px", borderRadius: 999, background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 12 }}>
            In your book
          </span>
        )}
      </div>

      {/* Field tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
        <Field label="Account owner" value={account.owner || "—"} highlight={ownerIsMe} youNote={ownerIsMe ? `That's you, ${you}` : undefined} />
        <Field label="BD owner" value={account.bdOwner || "—"} highlight={bdIsMe} youNote={bdIsMe ? `That's you, ${you}` : undefined} />
        <Field label="Type" value={account.type || "—"} />
        <Field label="Account status" value={account.status || "—"} chip status={account.status} />
      </div>
    </div>
  );
}

function Field({ label, value, highlight, youNote, chip, status }: {
  label: string; value: string; highlight?: boolean; youNote?: string; chip?: boolean; status?: string;
}) {
  return (
    <div style={{ padding: "14px 18px", borderTop: "1px solid var(--ia-gray-1)", borderRight: "1px solid var(--ia-gray-1)", background: highlight ? "var(--ia-blue-soft)" : "transparent" }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>
      {chip && status ? (
        <StatusChip value={status} />
      ) : (
        <div style={{ fontWeight: 600, fontSize: 15, color: highlight ? "var(--ia-blue-dark)" : "var(--ia-black)", overflow: "hidden", textOverflow: "ellipsis" }}>
          {value}
        </div>
      )}
      {youNote && <div className="label" style={{ marginTop: 4, fontSize: 11, color: "var(--ia-blue)" }}>{youNote}</div>}
    </div>
  );
}

function StatusChip({ value }: { value: string }) {
  const v = value.toLowerCase();
  const positive = /(active|customer|won|closed won|existing)/.test(v);
  const warm = /(prospect|open|target|pipeline|lead|negoti)/.test(v);
  const bg = positive ? "var(--ia-blue-soft)" : warm ? "#fff1e8" : "var(--ia-gray-1)";
  const color = positive ? "var(--ia-blue-dark)" : warm ? "var(--ia-orange)" : "var(--ia-gray-3)";
  return <span className="label" style={{ display: "inline-block", padding: "4px 11px", borderRadius: 999, background: bg, color, fontWeight: 600, fontSize: 13 }}>{value}</span>;
}

function SalesforceGlyph({ color }: { color: string }) {
  // A simple cloud mark — evokes Salesforce without using their trademarked logo.
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden style={{ flexShrink: 0 }}>
      <path d="M8.5 18.5a4 4 0 0 1-.6-7.96 4.5 4.5 0 0 1 8.36-1.7A3.5 3.5 0 1 1 17 18.5H8.5Z" fill={color} opacity="0.9" />
    </svg>
  );
}
