/**
 * app.ts — the Hono application (API routes only). Shared by two entry points:
 *   - server/index.ts : a long-running Node server (local dev / Render / Fly), which
 *     also serves the built SPA from dist/.
 *   - api/[[...route]].ts : a Vercel serverless function (static SPA served by Vercel).
 *
 * Route handlers live under src/routes/api/public/*.ts and are imported ONLY here,
 * never by the client bundle, so server secrets never reach browser code.
 */

import { Hono } from "hono";
import { cors } from "hono/cors";

import { scanEdgar } from "../src/routes/api/public/scan-edgar";
import { scanTechstack } from "../src/routes/api/public/scan-techstack";
import { scanNews } from "../src/routes/api/public/scan-news";
import { scanSerp } from "../src/routes/api/public/scan-serp";
import { scanJobs } from "../src/routes/api/public/providers/jobs-provider";
import { scanFunding } from "../src/routes/api/public/providers/funding-provider";
import { apolloContacts } from "../src/routes/api/public/apollo-contacts";
import { accountInfoForCard } from "../src/routes/api/public/account-info";
import { ask } from "../src/routes/api/public/ask";
import { readCache, writeCache } from "./cache";
import { registerAuth, sessionEmail, isAdminEmail } from "./auth";
import { accountsForUser, topAccountsForUser, accountByDomain, sheetsConfigured, readAccounts, domainKey, crmContext, type SheetAccount } from "./sheets";
import { personDigest, execRollup } from "../src/routes/api/public/providers/digest-provider";
import { competitorFootprint } from "../src/routes/api/public/providers/competitor-provider";
import { sendEmail, mailerConfigured } from "./mailer";

const now = () => Date.now();

export const app = new Hono();
app.use("/api/*", cors());

// Google SSO (domain-restricted). Registers /auth/*, /api/auth/me, and the guard
// on /api/public/* — MUST be before the /api/public route handlers below.
registerAuth(app);

interface ScanBody {
  company?: string;
  domain?: string;
}

async function readBody(c: { req: { json: () => Promise<unknown> } }): Promise<ScanBody> {
  try {
    return ((await c.req.json()) as ScanBody) ?? {};
  } catch {
    return {};
  }
}

app.post("/api/public/scan-edgar", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await scanEdgar({ company, domain }));
});

app.post("/api/public/scan-techstack", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await scanTechstack({ company, domain }));
});

app.post("/api/public/scan-news", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await scanNews({ company, domain }));
});

// Individual dedicated sources, exposed for auditability / testing.
app.post("/api/public/scan-serp", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await scanSerp({ company, domain }));
});

app.post("/api/public/scan-jobs", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await scanJobs(company, domain));
});

app.post("/api/public/scan-funding", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await scanFunding({ company, domain }));
});

app.post("/api/public/apollo-contacts", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await apolloContacts({ company, domain }));
});

// Competitor footprint — verifiable public evidence a target uses/evaluates an
// Impact Analytics competitor. On-demand (button) to keep credit use controlled.
app.post("/api/public/competitor-footprint", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await competitorFootprint({ company, domain }));
});

app.post("/api/public/account-info", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await accountInfoForCard({ company, domain }));
});

app.post("/api/public/ask", async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as { question?: string; company?: string; domain?: string };
  // Feed the connected Salesforce sheet as CRM context (relevance-matched).
  const crm = await crmContext(body.question ?? "", body.company, body.domain).catch(() => "");
  return c.json(await ask({ question: body.question ?? "", company: body.company, domain: body.domain, crm }));
});

// 30-day cache read/write (best-effort; on serverless it degrades gracefully).
app.get("/api/public/scan-cache", (c) => {
  const domain = c.req.query("domain") || "";
  if (!domain) return c.json({ hit: false });
  const hit = readCache(domain, now());
  return c.json({ hit: hit.hit, result: hit.result ?? null, ageMs: hit.ageMs ?? null });
});

app.post("/api/public/scan-cache", async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as {
    domain?: string;
    company?: string;
    result?: unknown;
  };
  if (body.domain && body.result) {
    writeCache(body.domain, body.company || "", body.result, now());
  }
  return c.json({ ok: true });
});

// Salesforce accounts pulled live from a private Google Sheet (service-account
// auth, server-side only). The FULL book is NEVER sent to the browser — every
// scope is limited to the signed-in user's own accounts:
//   scope=top  -> the user's accounts that are ALSO Tier_1__c = TRUE (default)
//   scope=mine -> all of the user's accounts (Owner or BD Owner match)
// Behind the /api/public/* auth guard.
app.get("/api/public/accounts", async (c) => {
  if (!sheetsConfigured()) {
    return c.json({ ok: false, configured: false, accounts: [], error: "Google Sheet not connected" });
  }
  try {
    const force = c.req.query("refresh") === "1";
    const email = sessionEmail(c) ?? undefined;
    const scope = c.req.query("scope") === "mine" ? "mine" : "top";
    const accounts = scope === "mine"
      ? await accountsForUser(email, force)
      : await topAccountsForUser(email, force);
    return c.json({ ok: true, configured: true, scope, accounts, count: accounts.length });
  } catch (e) {
    return c.json({ ok: false, configured: true, accounts: [], error: (e as Error).message }, 502);
  }
});

// Single account by website domain — for the CRM card on a scan. Returns one row
// (or null), never the whole book.
app.get("/api/public/account-lookup", async (c) => {
  if (!sheetsConfigured()) return c.json({ ok: false, configured: false, account: null });
  try {
    const account = await accountByDomain(c.req.query("domain") || "");
    return c.json({ ok: true, configured: true, account });
  } catch (e) {
    return c.json({ ok: false, configured: true, account: null, error: (e as Error).message }, 502);
  }
});

// ── Admin: team intelligence ────────────────────────────────────────────────
// Aggregates every person named in Owner.Name / BD_Owner__r across the Tier 1
// accounts, derives each one's email, and attaches any cached scan intelligence
// per account, so an admin can email each person a digest of THEIR top accounts.
// Admin-only (403 otherwise), on top of the /api/public/* auth guard.
const IGNORE_OWNER = /^(unassigned|n\/?a|none|-|marketing team)$/i;

function nameToEmail(name: string): string {
  const parts = name.toLowerCase().replace(/[^a-z\s]/g, " ").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  return `${parts.join(".")}@impactanalytics.co`;
}

interface IntelSummary {
  total: number; found: number; keyFound: number; supFound: number;
  top: Array<{ label: string; detail: string; type: string; soWhat: string }>;
  ageMs: number | null;
}

function intelForDomain(domain: string, now: number): IntelSummary | null {
  const hit = readCache(domainKey(domain), now);
  if (!hit.hit || !hit.result) return null;
  const r = hit.result as { signals?: Array<{ found?: boolean; label?: string; detail?: string; type?: string; group?: string; soWhat?: string }> };
  const sigs = r.signals ?? [];
  const found = sigs.filter((s) => s.found);
  const top = found.slice(0, 3).map((s) => ({ label: String(s.label ?? ""), detail: String(s.detail ?? ""), type: String(s.type ?? ""), soWhat: String(s.soWhat ?? "") }));
  return {
    total: sigs.length,
    found: found.length,
    keyFound: found.filter((s) => s.group === "key").length,
    supFound: found.filter((s) => s.group === "supporting").length,
    top,
    ageMs: hit.ageMs ?? null,
  };
}

app.get("/api/public/admin/owners", async (c) => {
  if (!isAdminEmail(sessionEmail(c))) return c.json({ ok: false, error: "forbidden" }, 403);
  if (!sheetsConfigured()) return c.json({ ok: false, configured: false, people: [] });
  try {
    const { accounts } = await readAccounts();
    const tier1 = accounts.filter((a) => a.tier1);
    const byPerson = new Map<string, { name: string; accounts: SheetAccount[] }>();
    const add = (personName: string | undefined, a: SheetAccount) => {
      const name = (personName || "").trim();
      if (!name || IGNORE_OWNER.test(name)) return;
      const key = name.toLowerCase();
      let p = byPerson.get(key);
      if (!p) { p = { name, accounts: [] }; byPerson.set(key, p); }
      if (!p.accounts.some((x) => x.domain === a.domain)) p.accounts.push(a);
    };
    for (const a of tier1) {
      add(a.owner, a);
      if (a.bdOwner && a.bdOwner.toLowerCase() !== a.owner.toLowerCase()) add(a.bdOwner, a);
    }
    const now = Date.now();
    const people = [...byPerson.values()]
      .map((p) => ({
        name: p.name,
        email: nameToEmail(p.name),
        accounts: p.accounts.map((a) => ({
          name: a.name,
          domain: domainKey(a.domain),
          type: a.type,
          status: a.status,
          revenue: a.revenue,
          owner: a.owner,
          bdOwner: a.bdOwner,
          intel: intelForDomain(a.domain, now),
        })),
      }))
      .sort((x, y) => y.accounts.length - x.accounts.length);
    return c.json({ ok: true, configured: true, people, count: people.length });
  } catch (e) {
    return c.json({ ok: false, configured: true, error: (e as Error).message }, 502);
  }
});

// Admin: executive roll-up across EVERYONE's Tier 1 accounts (for CXOs).
app.post("/api/public/admin/exec-rollup", async (c) => {
  if (!isAdminEmail(sessionEmail(c))) return c.json({ ok: false, error: "forbidden" }, 403);
  if (!sheetsConfigured()) return c.json({ ok: false, configured: false, error: "sheet not connected" });
  try {
    const { accounts } = await readAccounts();
    const tier1 = accounts.filter((a) => a.tier1);
    // De-dupe accounts by domain; collect the roster of owners/BD owners.
    const seen = new Set<string>();
    const uniq: Array<{ name: string; domain: string }> = [];
    const owners = new Set<string>();
    for (const a of tier1) {
      const key = domainKey(a.domain) || a.name.toLowerCase();
      if (a.owner) owners.add(a.owner.trim().toLowerCase());
      if (a.bdOwner) owners.add(a.bdOwner.trim().toLowerCase());
      if (key && !seen.has(key)) { seen.add(key); uniq.push({ name: a.name, domain: domainKey(a.domain) }); }
    }
    const r = await execRollup(uniq);
    return c.json({ ...r, generatedAt: now(), stats: { accounts: uniq.length, owners: owners.size } });
  } catch (e) {
    return c.json({ ok: false, overview: "", highlights: [], error: (e as Error).message }, 502);
  }
});

// Admin: last-7-days digest of developments across ONE person's top accounts.
app.post("/api/public/admin/person-digest", async (c) => {
  if (!isAdminEmail(sessionEmail(c))) return c.json({ ok: false, error: "forbidden" }, 403);
  const body = (await c.req.json().catch(() => ({}))) as { name?: string; accounts?: Array<{ name?: string; domain?: string }> };
  const accounts = (body.accounts ?? []).map((a) => ({ name: String(a.name ?? ""), domain: String(a.domain ?? "") }));
  const r = await personDigest(String(body.name ?? ""), accounts);
  return c.json({ ...r, generatedAt: now() });
});

// Admin: send a rendered HTML digest email (Resend). Admin-only.
app.post("/api/public/admin/send-email", async (c) => {
  if (!isAdminEmail(sessionEmail(c))) return c.json({ ok: false, error: "forbidden" }, 403);
  if (!mailerConfigured()) return c.json({ ok: false, error: "email_not_configured" });
  const body = (await c.req.json().catch(() => ({}))) as { to?: string; subject?: string; html?: string };
  const to = String(body.to ?? "").trim();
  const subject = String(body.subject ?? "").trim() || "Account Intelligence";
  const html = String(body.html ?? "");
  if (!to || !html) return c.json({ ok: false, error: "to and html are required" });
  return c.json(await sendEmail(to, subject, html));
});

app.get("/api/health", (c) => c.json({ ok: true }));
