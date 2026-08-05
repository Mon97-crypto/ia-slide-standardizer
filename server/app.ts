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
import { registerAuth } from "./auth";
import { readAccounts, sheetsConfigured } from "./sheets";

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

app.post("/api/public/account-info", async (c) => {
  const { company = "", domain = "" } = await readBody(c);
  return c.json(await accountInfoForCard({ company, domain }));
});

app.post("/api/public/ask", async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as { question?: string; company?: string; domain?: string };
  return c.json(await ask({ question: body.question ?? "", company: body.company, domain: body.domain }));
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
// auth, server-side only). Behind the /api/public/* auth guard.
app.get("/api/public/accounts", async (c) => {
  if (!sheetsConfigured()) {
    return c.json({ ok: false, configured: false, accounts: [], error: "Google Sheet not connected" });
  }
  try {
    const force = c.req.query("refresh") === "1";
    const { accounts, updatedAt, count } = await readAccounts(force);
    return c.json({ ok: true, configured: true, accounts, updatedAt, count });
  } catch (e) {
    return c.json({ ok: false, configured: true, accounts: [], error: (e as Error).message }, 502);
  }
});

app.get("/api/health", (c) => c.json({ ok: true }));
