/**
 * sheets.ts — read a PRIVATE Google Sheet server-side via a Google service
 * account. The sheet is never made public: it is simply shared (Viewer) with the
 * service account's email. Enterprise-safe by construction:
 *   - The service-account private key lives ONLY in server env (never the browser,
 *     never committed). We sign a short-lived RS256 JWT with node:crypto and
 *     exchange it for a Google access token — no third-party dependency.
 *   - Read-only scope (spreadsheets.readonly).
 *   - Rows are cached in-memory (default 10 min) so we don't hammer the Sheets API.
 *
 * Required env (set on Render, unset locally = feature disabled/open):
 *   GOOGLE_SHEET_ID          the id in the sheet URL: .../d/<THIS>/edit
 *   GOOGLE_SA_EMAIL          service account client_email
 *   GOOGLE_SA_PRIVATE_KEY    service account private_key (\n-escaped is fine)
 * Optional:
 *   GOOGLE_SHEET_RANGE       A1 range / tab, default "A:Z"
 *   GOOGLE_SHEET_TTL_MS      cache TTL in ms, default 600000 (10 min)
 */

import { createSign } from "node:crypto";

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly";

export function sheetsConfigured(): boolean {
  return !!(process.env.GOOGLE_SHEET_ID && process.env.GOOGLE_SA_EMAIL && process.env.GOOGLE_SA_PRIVATE_KEY);
}

function privateKey(): string {
  // Render/env stores newlines as the two-character sequence \n — restore them.
  return (process.env.GOOGLE_SA_PRIVATE_KEY as string).replace(/\\n/g, "\n");
}

function b64url(input: string | Buffer): string {
  return Buffer.from(input).toString("base64url");
}

// ---- access-token cache (a token is valid ~1h; we refresh a minute early) ----
let tokenCache: { token: string; exp: number } | null = null;

async function accessToken(): Promise<string> {
  const nowSec = Math.floor(Date.now() / 1000);
  if (tokenCache && tokenCache.exp - 60 > nowSec) return tokenCache.token;

  const header = b64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claims = b64url(
    JSON.stringify({
      iss: process.env.GOOGLE_SA_EMAIL,
      scope: SCOPE,
      aud: TOKEN_URL,
      iat: nowSec,
      exp: nowSec + 3600,
    }),
  );
  const signingInput = `${header}.${claims}`;
  const signature = createSign("RSA-SHA256").update(signingInput).sign(privateKey(), "base64url");
  const assertion = `${signingInput}.${signature}`;

  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion,
    }),
  });
  if (!res.ok) {
    throw new Error(`Google token exchange failed (${res.status}): ${(await res.text()).slice(0, 300)}`);
  }
  const data = (await res.json()) as { access_token: string; expires_in: number };
  tokenCache = { token: data.access_token, exp: nowSec + (data.expires_in ?? 3600) };
  return data.access_token;
}

export interface SheetAccount {
  domain: string;      // Domain_Text__c — account website
  name: string;        // Name — account name
  owner: string;       // Owner.Name
  bdOwner: string;     // BD_Owner__r
  type: string;        // Type
  status: string;      // Account_Status__c
  revenue: string;     // AnnualRevenue (raw text as in the sheet)
  raw: Record<string, string>;
}

// Map a header cell to a canonical key. Tolerant of case / spacing / punctuation
// so small changes to the Salesforce export column labels don't break the mapping.
function canonHeader(h: string): keyof SheetAccount | null {
  const k = h.toLowerCase().replace(/[^a-z]/g, "");
  if (k.includes("domain") || k === "website" || k === "url") return "domain";
  if (k === "name" || k === "accountname") return "name";
  if (k.includes("ownername") || k === "owner") return "owner";
  if (k.includes("bdowner") || k.includes("bdownerr")) return "bdOwner";
  if (k === "type") return "type";
  if (k.includes("accountstatus") || k === "status") return "status";
  if (k.includes("annualrevenue") || k === "revenue") return "revenue";
  return null;
}

// ---- row cache ----
let rowCache: { at: number; accounts: SheetAccount[] } | null = null;

export interface SheetResult {
  accounts: SheetAccount[];
  updatedAt: number;
  count: number;
}

export async function readAccounts(force = false): Promise<SheetResult> {
  const ttl = Number(process.env.GOOGLE_SHEET_TTL_MS ?? 600_000);
  if (!force && rowCache && Date.now() - rowCache.at < ttl) {
    return { accounts: rowCache.accounts, updatedAt: rowCache.at, count: rowCache.accounts.length };
  }

  const token = await accessToken();
  const id = process.env.GOOGLE_SHEET_ID as string;
  const range = process.env.GOOGLE_SHEET_RANGE ?? "A:Z";
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(id)}/values/${encodeURIComponent(range)}?majorDimension=ROWS`;
  const res = await fetch(url, { headers: { authorization: `Bearer ${token}` } });
  if (!res.ok) {
    throw new Error(`Sheets read failed (${res.status}): ${(await res.text()).slice(0, 300)}`);
  }
  const data = (await res.json()) as { values?: string[][] };
  const rows = data.values ?? [];
  if (rows.length < 2) {
    rowCache = { at: Date.now(), accounts: [] };
    return { accounts: [], updatedAt: rowCache.at, count: 0 };
  }

  const headers = rows[0].map((h) => (h ?? "").trim());
  const cols = headers.map(canonHeader);

  const accounts: SheetAccount[] = [];
  for (const row of rows.slice(1)) {
    const raw: Record<string, string> = {};
    const rec: SheetAccount = { domain: "", name: "", owner: "", bdOwner: "", type: "", status: "", revenue: "", raw };
    headers.forEach((h, i) => {
      const v = (row[i] ?? "").toString().trim();
      raw[h] = v;
      const key = cols[i];
      if (key && key !== "raw" && v) rec[key] = v;
    });
    // Skip empty rows (no name and no website).
    if (!rec.name && !rec.domain) continue;
    accounts.push(rec);
  }

  rowCache = { at: Date.now(), accounts };
  return { accounts, updatedAt: rowCache.at, count: accounts.length };
}
