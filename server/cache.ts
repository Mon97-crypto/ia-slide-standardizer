/**
 * cache.ts — the 24-hour `scans` cache. A Supabase table in the original spec;
 * here a small JSON-file store with the same contract (unique by domain, 24h TTL).
 * The interface is deliberately narrow so it can be swapped for a real DB later.
 */

import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = process.env.SCAN_CACHE_DIR || join(__dirname, "..", ".data");
const CACHE_FILE = join(DATA_DIR, "scans.json");
const TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30-day cache

// Bump whenever the scan pipeline's accuracy logic changes, so a deploy ignores
// every previously-cached (stale) scan instead of serving it for up to 30 days.
const CACHE_VERSION = 3;

interface CacheRow {
  domain: string;
  company: string;
  result: unknown;
  created_at: number;
  v?: number;
}

type CacheShape = Record<string, CacheRow>;

function load(): CacheShape {
  try {
    if (!existsSync(CACHE_FILE)) return {};
    return JSON.parse(readFileSync(CACHE_FILE, "utf8")) as CacheShape;
  } catch {
    return {};
  }
}

function save(data: CacheShape): void {
  try {
    mkdirSync(DATA_DIR, { recursive: true });
    writeFileSync(CACHE_FILE, JSON.stringify(data), "utf8");
  } catch {
    // cache is best-effort; ignore write failures.
  }
}

export interface CacheHit {
  hit: boolean;
  result?: unknown;
  ageMs?: number;
}

export function readCache(domain: string, now: number): CacheHit {
  const row = load()[domain.toLowerCase()];
  if (!row) return { hit: false };
  if (row.v !== CACHE_VERSION) return { hit: false }; // stale pre-upgrade result
  const ageMs = now - row.created_at;
  if (ageMs > TTL_MS) return { hit: false };
  return { hit: true, result: injectAge(row.result, ageMs), ageMs };
}

function injectAge(result: unknown, ageMs: number): unknown {
  if (result && typeof result === "object") {
    return { ...(result as Record<string, unknown>), cached: true, cachedAgeMs: ageMs };
  }
  return result;
}

export function writeCache(
  domain: string,
  company: string,
  result: unknown,
  now: number,
): void {
  const data = load();
  data[domain.toLowerCase()] = {
    domain: domain.toLowerCase(),
    company,
    result,
    created_at: now,
    v: CACHE_VERSION,
  };
  save(data);
}
