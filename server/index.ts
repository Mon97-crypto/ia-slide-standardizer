/**
 * server/index.ts — long-running Node entry point (local dev, Render, Fly, etc.).
 * Imports the shared Hono app, adds SPA static serving from dist/, and listens.
 * On Vercel this file is NOT used; api/[[...route]].ts serves the API instead.
 */

import { serve } from "@hono/node-server";
import { serveStatic } from "@hono/node-server/serve-static";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { app } from "./app";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DIST = join(__dirname, "..", "dist");
const PORT = Number(process.env.PORT || 8787);

// Serve the built SPA. Static files (assets, logo, favicon) are served from dist
// first; anything else falls back to index.html for client-side routes.
if (existsSync(DIST)) {
  app.get("*", serveStatic({ root: "./dist" }));
  app.get("*", serveStatic({ path: "./dist/index.html" }));
}

serve({ fetch: app.fetch, port: PORT }, (info) => {
  // eslint-disable-next-line no-console
  console.log(`IA Account Scanner listening on http://localhost:${info.port}`);
});
