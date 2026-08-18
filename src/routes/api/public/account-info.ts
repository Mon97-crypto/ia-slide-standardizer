/**
 * account-info.ts — accurate firmographics for the EXACT company being scanned.
 *
 * Everything is keyed off the domain the user entered (never the company name),
 * so the result always belongs to the same company — no fila.com-style mismatch.
 *
 * Source: Apollo organization enrichment (GET /organizations/enrich?domain=…),
 * which returns industry, revenue, HQ, website and the official logo for that
 * exact domain. Guarded by APOLLO_API_KEY (server-side only). Never throws.
 */

import { companyVerifyAvailable, verifyCompany } from "./providers/company-verify";

interface AccountInput {
  company: string;
  domain: string;
}

export interface AccountInfo {
  name: string;
  domain: string;
  industry: string | null;
  revenue: string | null;
  hq: string | null;
  website: string | null;
  logoUrl: string | null;
  employees: string | null;
  description: string | null;
  founded: string | null;
  ownership: string | null;
  /** true when the description/HQ were web-verified via Claude, not just Apollo. */
  verified: boolean;
  sources: string[];
}

interface ApolloOrg {
  name?: string;
  website_url?: string;
  primary_domain?: string;
  industry?: string;
  estimated_num_employees?: number;
  annual_revenue?: number;
  annual_revenue_printed?: string;
  city?: string;
  state?: string;
  country?: string;
  raw_address?: string;
  logo_url?: string;
  short_description?: string;
}

// A domain-keyed official logo, so it always matches the company being scanned.
function fallbackLogo(domain: string): string {
  return `https://logo.clearbit.com/${domain}`;
}

function formatRevenue(org: ApolloOrg): string | null {
  if (org.annual_revenue_printed) {
    const p = org.annual_revenue_printed.trim();
    return p.startsWith("$") ? p : `$${p}`;
  }
  const n = org.annual_revenue;
  if (typeof n === "number" && n > 0) {
    if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
    if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
    return `$${n}`;
  }
  return null;
}

function formatHq(org: ApolloOrg): string | null {
  const parts = [org.city, org.state, org.country].filter(Boolean);
  if (parts.length) return parts.join(", ");
  return org.raw_address?.trim() || null;
}

function formatEmployees(org: ApolloOrg): string | null {
  const n = org.estimated_num_employees;
  if (typeof n !== "number" || n <= 0) return null;
  return n.toLocaleString("en-US");
}

// In-memory memo so the account endpoint and the news classifier don't both
// spend an Apollo credit enriching the same domain within a server lifetime.
const memo = new Map<string, { at: number; value: { ok: boolean; account: AccountInfo | null; error?: string } }>();
const MEMO_TTL_MS = 30 * 24 * 60 * 60 * 1000;

/**
 * resolveEntity — the EXACT company for a domain: its official name and industry,
 * used to disambiguate search (e.g. "Gap Inc." not the word "gap", the sportswear
 * brand at fila.com not F.I.L.A. Group). Falls back to the caller's guess.
 */
export async function resolveEntity(
  company: string,
  domain: string,
): Promise<{ name: string; industry: string | null; description: string | null }> {
  const r = await accountInfo({ company, domain });
  const name = r.account?.name && r.account.name !== domain ? r.account.name : company;
  return { name, industry: r.account?.industry ?? null, description: r.account?.description ?? null };
}

/**
 * accountInfoForCard — the user-facing Account card. Starts from Apollo's
 * structured firmographics, then (when ANTHROPIC_API_KEY is set) overlays a
 * web-VERIFIED description + headquarters + founding + ownership so crucial facts
 * are current and correct rather than Apollo's sometimes-stale free text.
 */
export async function accountInfoForCard(
  input: AccountInput,
): Promise<{ ok: boolean; account: AccountInfo | null; error?: string }> {
  const base = await accountInfo(input);
  if (!base.account || !companyVerifyAvailable()) return base;
  try {
    const v = await verifyCompany(base.account.name, base.account.domain);
    if (!v) return base;
    const account: AccountInfo = {
      ...base.account,
      description: v.description || base.account.description,
      hq: v.headquarters || base.account.hq,
      founded: v.founded || base.account.founded,
      ownership: v.ownership || base.account.ownership,
      verified: Boolean(v.description || v.headquarters),
      sources: v.sources,
    };
    return { ...base, account };
  } catch {
    return base;
  }
}

export async function accountInfo(
  input: AccountInput,
): Promise<{ ok: boolean; account: AccountInfo | null; error?: string }> {
  const { domain } = input;
  if (!domain) return { ok: false, account: null, error: "domain is required" };

  const cached = memo.get(domain);
  if (cached && Date.now() - cached.at < MEMO_TTL_MS) return cached.value;

  // Baseline the card can always render, even if enrichment is unavailable.
  const baseline: AccountInfo = {
    name: input.company || domain,
    domain,
    industry: null,
    revenue: null,
    hq: null,
    website: `https://${domain}`,
    logoUrl: fallbackLogo(domain),
    employees: null,
    description: null,
    founded: null,
    ownership: null,
    verified: false,
    sources: [],
  };

  const apiKey = process.env.APOLLO_API_KEY;
  if (!apiKey) {
    return { ok: false, account: baseline, error: "APOLLO_API_KEY is not configured." };
  }

  try {
    const url = `https://api.apollo.io/api/v1/organizations/enrich?domain=${encodeURIComponent(domain)}`;
    const res = await fetch(url, {
      method: "GET",
      headers: { accept: "application/json", "x-api-key": apiKey },
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return { ok: false, account: baseline, error: `Apollo HTTP ${res.status}: ${body.slice(0, 160)}` };
    }
    const data = (await res.json()) as { organization?: ApolloOrg };
    const org = data.organization;
    if (!org) {
      const value = { ok: true, account: baseline };
      memo.set(domain, { at: Date.now(), value });
      return value;
    }

    const account: AccountInfo = {
      name: org.name || baseline.name,
      domain: org.primary_domain || domain,
      industry: org.industry
        ? org.industry.replace(/\b\w/g, (c) => c.toUpperCase())
        : null,
      revenue: formatRevenue(org),
      hq: formatHq(org),
      website: org.website_url || baseline.website,
      logoUrl: org.logo_url || fallbackLogo(domain),
      employees: formatEmployees(org),
      description: org.short_description?.trim() || null,
      founded: null,
      ownership: null,
      verified: false,
      sources: [],
    };
    const value = { ok: true, account };
    memo.set(domain, { at: Date.now(), value });
    return value;
  } catch (err) {
    return { ok: false, account: baseline, error: (err as Error).message };
  }
}
