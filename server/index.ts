/**
 * server/index.ts — a single Hono service that:
 *   - mounts the file-routed API handlers under /api/public/*
 *   - serves the built SPA from dist/ in production
 *
 * The route handlers live under src/routes/api/public/*.ts and are imported ONLY
 * here, never by the client bundle, so server secrets (ANTHROPIC_API_KEY,
 * APOLLO_API_KEY) can never leak into browser code.
 */

import { serve } from "@hono/node-server";
import { serveStatic } from "@hono/node-server/serve-static";
import { Hono } from "hono";
import { cors } from "hono/cors";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { scanEdgar } from "../src/routes/api/public/scan-edgar";
import { scanTechstack } from "../src/routes/api/public/scan-techstack";
import { scanNews } from "../src/routes/api/public/scan-news";
import { scanSerp } from "../src/routes/api/public/scan-serp";
import { scanJobs } from "../src/routes/api/public/providers/jobs-provider";
import { scanFunding } from "../src/routes/api/public/providers/funding-provider";
import { apolloContacts } from "../src/routes/api/public/apollo-contacts";
import { ask } from "../src/routes/api/public/ask";
import { readCache, writeCache } from "./cache";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DIST = join(__dirname, "..", "dist");
const PORT = Number(process.env.PORT || 8787);

// A stable clock so scripts stay deterministic-friendly; Date.now is fine here.
const now = () => Date.now();

const app = new Hono();
app.use("/api/*", cors());

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

app.post("/api/public/ask", async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as { question?: string; company?: string; domain?: string };
  return c.json(await ask({ question: body.question ?? "", company: body.company, domain: body.domain }));
});

// 24h cache read/write.
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

app.get("/api/health", (c) => c.json({ ok: true }));

// Serve the built SPA (production). Static files (assets, logo, favicon) are
// served from dist first; anything else falls back to index.html for client routes.
if (existsSync(DIST)) {
  app.get("*", serveStatic({ root: "./dist" }));
  app.get("*", serveStatic({ path: "./dist/index.html" }));
}

serve({ fetch: app.fetch, port: PORT }, (info) => {
  // eslint-disable-next-line no-console
  console.log(`IA Account Scanner listening on http://localhost:${info.port}`);
});
