/**
 * ScanForm — autofocuses the website field on load, Enter submits from any field,
 * accepts a bare domain / full URL / pasted URL with tracking params and
 * normalizes silently. The button keeps its verb through the flow: "Run scan".
 */
import { useEffect, useRef, useState } from "react";
import { companyFromDomain, normalizeDomain } from "../lib/normalize";

export interface ScanRequest {
  company: string;
  domain: string;
}

export function ScanForm({
  onScan,
  scanning,
  prefill,
}: {
  onScan: (req: ScanRequest) => void;
  scanning: boolean;
  prefill?: ScanRequest | null;
}) {
  const [website, setWebsite] = useState("");
  const [company, setCompany] = useState("");
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  // Reflect a scan started from the dashboard in the form fields.
  useEffect(() => {
    if (prefill) {
      setWebsite(prefill.domain);
      setCompany(prefill.company);
    }
  }, [prefill]);

  function submit() {
    const domain = normalizeDomain(website);
    if (!domain) {
      ref.current?.focus();
      return;
    }
    onScan({ domain, company: company.trim() || companyFromDomain(domain) });
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      style={{ display: "grid", gap: 12 }}
    >
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" }}>
        <label style={{ display: "grid", gap: 6 }}>
          <span className="eyebrow">Website</span>
          <input
            ref={ref}
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="acme.com"
            autoComplete="off"
            spellCheck={false}
            style={inputStyle}
          />
        </label>
        <label style={{ display: "grid", gap: 6 }}>
          <span className="eyebrow">Company (optional)</span>
          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="Acme Retail"
            autoComplete="off"
            style={inputStyle}
          />
        </label>
      </div>
      <div>
        <button type="submit" disabled={scanning} style={buttonStyle(scanning)}>
          {scanning ? "Scanning…" : "Run scan"}
        </button>
        <span className="secondary" style={{ marginLeft: 12 }}>
          Paste a full URL or a bare domain. We clean it up.
        </span>
      </div>
    </form>
  );
}

const inputStyle: React.CSSProperties = {
  height: 44,
  padding: "0 14px",
  borderRadius: 13,
  border: "1px solid var(--ia-gray-1)",
  background: "var(--ia-white)",
  fontSize: 15,
  fontFamily: "inherit",
  color: "var(--ia-black)",
};

function buttonStyle(disabled: boolean): React.CSSProperties {
  return {
    height: 44,
    padding: "0 22px",
    borderRadius: 13,
    border: "none",
    background: disabled ? "var(--ia-blue-light)" : "var(--ia-blue)",
    color: "var(--ia-white)",
    fontWeight: 600,
    fontSize: 15,
    transition: "background 180ms cubic-bezier(.22,.61,.36,1)",
  };
}
