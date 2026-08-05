/**
 * accounts-sheet.ts — client access to the Salesforce accounts synced from the
 * private Google Sheet, plus the logic that (a) derives a friendly display name
 * from the logged-in email and (b) decides which accounts "belong" to a user by
 * matching that name against the Owner.Name and BD_Owner__r columns.
 */

export interface SheetAccount {
  domain: string;
  name: string;
  owner: string;
  bdOwner: string;
  type: string;
  status: string;
  revenue: string;
  raw: Record<string, string>;
}

export interface AccountsResponse {
  ok: boolean;
  configured: boolean;
  accounts: SheetAccount[];
  updatedAt?: number;
  count?: number;
  error?: string;
}

export async function fetchAccounts(refresh = false): Promise<AccountsResponse> {
  try {
    const res = await fetch(`/api/public/accounts${refresh ? "?refresh=1" : ""}`);
    return (await res.json()) as AccountsResponse;
  } catch (e) {
    return { ok: false, configured: true, accounts: [], error: (e as Error).message };
  }
}

// Shared, in-flight-deduped fetch so the dashboard and the scan lookup reuse one
// request instead of hitting the endpoint twice.
let accountsPromise: Promise<AccountsResponse> | null = null;
export function getAccountsCached(refresh = false): Promise<AccountsResponse> {
  if (refresh) accountsPromise = null;
  if (!accountsPromise) accountsPromise = fetchAccounts(refresh);
  return accountsPromise;
}

// Normalize a domain for comparison: lowercase, drop scheme/www/path.
function domainKey(raw: string): string {
  return (raw || "")
    .toLowerCase()
    .trim()
    .replace(/^[a-z]+:\/\//, "")
    .replace(/^www\./, "")
    .split(/[/?#]/)[0]
    .trim();
}

/** Find the Salesforce row whose Domain_Text__c matches this website, if any. */
export async function findAccountByDomain(domain: string): Promise<SheetAccount | null> {
  const key = domainKey(domain);
  if (!key) return null;
  const r = await getAccountsCached();
  if (!r.ok) return null;
  return r.accounts.find((a) => domainKey(a.domain) === key) ?? null;
}

/** "monica.a@impactanalytics.co" -> "Monica A". Falls back gracefully. */
export function displayNameFromEmail(email: string | undefined): string {
  if (!email) return "there";
  const local = email.split("@")[0] || "";
  const tokens = local.split(/[._-]+/).filter(Boolean);
  if (!tokens.length) return "there";
  return tokens.map((t) => t.charAt(0).toUpperCase() + t.slice(1)).join(" ");
}

/** Lowercased alphabetic tokens from the email local part: monica.a -> ["monica","a"]. */
export function nameTokensFromEmail(email: string | undefined): string[] {
  if (!email) return [];
  const local = email.split("@")[0] || "";
  return local
    .toLowerCase()
    .split(/[._\-+]+/)
    .map((t) => t.replace(/[^a-z]/g, ""))
    .filter(Boolean);
}

function ownerTokens(field: string): string[] {
  return field
    .toLowerCase()
    .replace(/[^a-z]+/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

/**
 * Does an owner field (Owner.Name or BD_Owner__r) belong to the user whose email
 * yields `tokens`? Requires the first name to appear, and — when a surname/initial
 * is known — a surname token that matches by prefix in either direction, so
 * "monica.a" matches both "Monica A" and "Monica Agarwal", and "monica.agarwal"
 * matches "Monica A". Order-independent (handles "Agarwal, Monica" too).
 */
export function ownerMatches(field: string | undefined, tokens: string[]): boolean {
  if (!field || tokens.length === 0) return false;
  const o = ownerTokens(field);
  if (!o.length) return false;
  const first = tokens[0];
  if (!o.includes(first)) return false;
  if (tokens.length === 1) return true;
  const last = tokens[tokens.length - 1];
  return o.some((t) => t !== first && (t.startsWith(last) || last.startsWith(t)));
}

/** An account is "mine" if either the Owner or the BD Owner matches the user. */
export function isMine(a: SheetAccount, tokens: string[]): boolean {
  return ownerMatches(a.owner, tokens) || ownerMatches(a.bdOwner, tokens);
}

/** Best-effort revenue formatting: numbers -> $1.2M / $940K, else pass through. */
export function formatRevenue(raw: string): string {
  if (!raw) return "—";
  const n = Number(raw.replace(/[^0-9.]/g, ""));
  if (!raw.match(/^[\s$]*[\d.,]+\s*$/) || !isFinite(n) || n === 0) return raw;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1).replace(/\.0$/, "")}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${n}`;
}
