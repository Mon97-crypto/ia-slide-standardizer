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

export async function accountInfo(
  input: AccountInput,
): Promise<{ ok: boolean; account: AccountInfo | null; error?: string }> {
  const { domain } = input;
  if (!domain) return { ok: false, account: null, error: "domain is required" };

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
    if (!org) return { ok: true, account: baseline };

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
    };
    return { ok: true, account };
  } catch (err) {
    return { ok: false, account: baseline, error: (err as Error).message };
  }
}
