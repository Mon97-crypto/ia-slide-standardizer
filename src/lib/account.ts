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
  founded: string | null;
  ownership: string | null;
  verified: boolean;
  sources: string[];
}

const TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days
// v2: only web-verified accounts are cached, so a stale unverified entry can never
// pin the wrong facts. Bumping the prefix also discards all pre-upgrade entries.
const KEY = (domain: string) => `ia-account:v2:${domain}`;

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
    if (data.account) {
      // Only cache web-VERIFIED accounts. An unverified one (e.g. the Anthropic key
      // was missing) must be re-fetched next time so it can be corrected, not pinned.
      if (data.ok && data.account.verified) writeCache(domain, data.account);
      return data.account;
    }
    return null;
  } catch {
    return null;
  }
}
