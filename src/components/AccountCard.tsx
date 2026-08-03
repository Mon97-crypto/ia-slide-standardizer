/**
 * AccountCard — the "Account information" section: the exact company's logo
 * (fetched from its official domain), name, industry, revenue, HQ and website.
 * Built to the IA brand system — Impact Blue, Off-White, Spectral headings.
 */
import { useState } from "react";
import type { AccountInfo } from "../lib/account";

export function AccountCard({ account, loading }: { account: AccountInfo | null; loading: boolean }) {
  if (loading && !account) {
    return (
      <section className="card" style={{ padding: 22, display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ width: 68, height: 68, borderRadius: 16, background: "var(--ia-blue-soft)" }} />
        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ width: 200, height: 18, borderRadius: 6, background: "var(--ia-gray-1)" }} />
          <div style={{ width: 140, height: 13, borderRadius: 6, background: "var(--ia-gray-1)" }} />
        </div>
        <span className="secondary" style={{ marginLeft: "auto" }}>Loading account…</span>
      </section>
    );
  }
  if (!account) return null;

  const websiteHost = account.website ? account.website.replace(/^https?:\/\//, "").replace(/\/$/, "") : account.domain;

  return (
    <section className="card" style={{ padding: 0, overflow: "hidden" }}>
      {/* Header band — logo + identity on a soft Impact Blue gradient. */}
      <div style={{ display: "flex", alignItems: "center", gap: 18, padding: "22px 24px", background: "linear-gradient(160deg, var(--ia-blue-soft) 0%, var(--ia-white) 72%)" }}>
        <CompanyLogo domain={account.domain} name={account.name} logoUrl={account.logoUrl} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>Account information</div>
          <h2 className="h2" style={{ margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{account.name}</h2>
          <a href={account.website || `https://${account.domain}`} target="_blank" rel="noreferrer" className="label" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--ia-blue)" }} />
            {websiteHost}
          </a>
        </div>
      </div>

      {account.description && (
        <p className="secondary" style={{ margin: 0, padding: "0 24px 16px", maxWidth: 720 }}>
          {account.description.length > 220 ? `${account.description.slice(0, 220)}…` : account.description}
        </p>
      )}

      {/* Firmographic grid — crisp 1px dividers via a gray gap. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 1, background: "var(--ia-gray-1)", borderTop: "1px solid var(--ia-gray-1)" }}>
        <Field label="Industry" value={account.industry} />
        <Field label="Revenue" value={account.revenue} accent />
        <Field label="HQ" value={account.hq} />
        <Field label="Website" value={websiteHost} href={account.website || `https://${account.domain}`} />
      </div>
    </section>
  );
}

function Field({ label, value, href, accent }: { label: string; value: string | null; href?: string; accent?: boolean }) {
  return (
    <div style={{ background: "var(--ia-white)", padding: "14px 18px", minWidth: 0 }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>
      {value ? (
        href ? (
          <a href={href} target="_blank" rel="noreferrer" className="card-title" style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</a>
        ) : (
          <div className="card-title" style={{ color: accent ? "var(--ia-blue)" : "var(--ia-black)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</div>
        )
      ) : (
        <div className="card-title" style={{ color: "var(--ia-gray-3)", fontWeight: 500 }}>—</div>
      )}
    </div>
  );
}

/**
 * CompanyLogo — tries the official logo, then a domain-keyed logo service, then a
 * favicon, and finally falls back to a brand-blue monogram. Every source is keyed
 * by the searched domain, so the mark always matches the exact company.
 */
function CompanyLogo({ domain, name, logoUrl }: { domain: string; name: string; logoUrl: string | null }) {
  const candidates = [
    logoUrl,
    `https://logo.clearbit.com/${domain}`,
    `https://www.google.com/s2/favicons?domain=${domain}&sz=128`,
  ].filter(Boolean) as string[];
  const [idx, setIdx] = useState(0);
  const exhausted = idx >= candidates.length;

  const tile: React.CSSProperties = {
    width: 68, height: 68, borderRadius: 16, flexShrink: 0,
    background: "var(--ia-white)", border: "1px solid var(--ia-gray-1)",
    boxShadow: "0 2px 10px rgba(20,20,30,0.06)",
    display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden",
  };

  if (exhausted) {
    return (
      <div style={{ ...tile, background: "var(--ia-blue)" }}>
        <span className="serif" style={{ color: "var(--ia-white)", fontSize: 30, lineHeight: 1 }}>
          {(name || domain).trim().charAt(0).toUpperCase()}
        </span>
      </div>
    );
  }
  return (
    <div style={tile}>
      <img
        src={candidates[idx]}
        alt={`${name} logo`}
        onError={() => setIdx((i) => i + 1)}
        style={{ maxWidth: "78%", maxHeight: "78%", objectFit: "contain" }}
      />
    </div>
  );
}
