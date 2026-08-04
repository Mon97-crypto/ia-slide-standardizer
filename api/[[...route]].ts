/**
 * api/[[...route]].ts — Vercel serverless entry point for the whole API.
 *
 * Vercel routes every /api/* request to this catch-all function; Hono then matches
 * the full path (/api/public/...) against the shared app. The Node.js runtime is
 * required because the handlers use node:fs / node:path (cache) and global fetch.
 *
 * maxDuration is set high because scan-news runs a deep search + LLM verification
 * that can take 60-120s. On Vercel Hobby this is capped at 60s and long scans may
 * time out; Vercel Pro honours up to 300s.
 */

import { handle } from "hono/vercel";
import { app } from "../server/app";

export const runtime = "nodejs";
export const maxDuration = 300;

export default handle(app);
