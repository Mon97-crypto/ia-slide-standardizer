/**
 * account.ts — client-side fetch for the Account Information section, with a
 * 30-day localStorage cache keyed by domain so re-scans are instant and Apollo
 * credits are not spent twice on the same company.
 */

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

const TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days
const KEY = (domain: string) => `ia-account:${domain}`;

function readCache(domain: string): AccountInfo | null {
  try {
    const raw = localStorage.getItem(KEY(domain));
    if (!raw) return null;
    const { at, account } = JSON.parse(raw) as { at: number; account: AccountInfo };
    if (Date.now() - at > TTL_MS) return null;
    return account;
  } catch {
    return null;
  }
}

function writeCache(domain: string, account: AccountInfo): void {
  try {
    localStorage.setItem(KEY(domain), JSON.stringify({ at: Date.now(), account }));
  } catch {
    // storage full / disabled — cache is best-effort.
  }
}

export async function fetchAccount(
  company: string,
  domain: string,
  signal?: AbortSignal,
): Promise<AccountInfo | null> {
  if (!domain) return null;
  const cached = readCache(domain);
  if (cached) return cached;
  try {
    const res = await fetch("/api/public/account-info", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ company, domain }),
      signal,
    });
    const data = (await res.json()) as { ok: boolean; account: AccountInfo | null };
    // Even a partial (baseline) account is worth showing and caching.
    if (data.account) {
      if (data.ok) writeCache(domain, data.account);
      return data.account;
    }
    return null;
  } catch {
    return null;
  }
}
