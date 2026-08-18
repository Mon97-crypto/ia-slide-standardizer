/**
 * digest-log.ts — server-side, shared-across-admins record of the admin "top
 * accounts" digests: which items each person has already been sent (cross-week
 * dedup), a send-history audit trail (when / how many / which channel), and the
 * exact items of the last digest (so any admin can re-send it).
 *
 * Same small JSON-file store as cache.ts. It lives in the server process, so all
 * admins share one truth instead of each browser keeping its own localStorage.
 * (On an ephemeral host the file resets on redeploy, exactly like the scan cache;
 * swap the load/save pair for a real DB to make it durable.)
 */

import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = process.env.SCAN_CACHE_DIR || join(__dirname, "..", ".data");
const LOG_FILE = join(DATA_DIR, "digest-log.json");

export type SendChannel = "email" | "gmail";
export interface SendRecord { at: string; count: number; channel?: SendChannel }
export interface DigestItem {
  account: string; domain: string; headline: string; detail: string; soWhat: string; url: string; date: string;
}

interface PersonLog {
  sent: Record<string, string>;   // itemKey -> YYYY-MM-DD  (cross-week dedup)
  history: SendRecord[];          // newest first, capped
  last: DigestItem[];             // items of the most recent digest (for re-send)
}
type Store = Record<string, PersonLog>;

function load(): Store {
  try {
    if (!existsSync(LOG_FILE)) return {};
    return JSON.parse(readFileSync(LOG_FILE, "utf8")) as Store;
  } catch { return {}; }
}
function save(data: Store): void {
  try {
    mkdirSync(DATA_DIR, { recursive: true });
    writeFileSync(LOG_FILE, JSON.stringify(data), "utf8");
  } catch { /* best-effort */ }
}

const key = (email: string) => email.trim().toLowerCase();
function person(store: Store, email: string): PersonLog {
  const k = key(email);
  if (!store[k]) store[k] = { sent: {}, history: [], last: [] };
  return store[k];
}

/** Stable de-dupe key for an item — must mirror the client's previous logic. */
function itemKey(it: DigestItem): string {
  const acct = (it.domain || it.account).toLowerCase().replace(/[^a-z0-9]/g, "");
  const head = (it.headline || "").toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 48);
  return `${acct}|${head}`;
}

/** The most recent send for a person (or inferred from the dedup log). */
export function lastSend(email: string): SendRecord | null {
  const p = load()[key(email)];
  if (!p) return null;
  if (p.history.length) return p.history[0];
  const dates = Object.values(p.sent).sort();
  if (!dates.length) return null;
  const at = dates[dates.length - 1];
  return { at, count: dates.filter((d) => d === at).length };
}

/** last-send record for many people at once (for the admin list). */
export function lastSendMany(emails: string[]): Record<string, SendRecord | null> {
  const out: Record<string, SendRecord | null> = {};
  for (const e of emails) out[e] = lastSend(e);
  return out;
}

/** Split a fresh pull into items not sent before vs. already sent (hidden). */
export function dedup(email: string, items: DigestItem[]): { fresh: DigestItem[]; skipped: number; last: DigestItem[] } {
  const store = load();
  const p = store[key(email)];
  const sent = p?.sent ?? {};
  const fresh: DigestItem[] = [];
  const seen = new Set<string>();
  let skipped = 0;
  for (const it of items) {
    const k = itemKey(it);
    if (seen.has(k)) continue;
    seen.add(k);
    if (sent[k]) { skipped++; continue; }
    fresh.push(it);
  }
  return { fresh, skipped, last: p?.last ?? [] };
}

/** Record a send: mark items sent, prepend a history record, stash the items. */
export function recordSend(email: string, items: DigestItem[], channel: SendChannel): SendRecord {
  const store = load();
  const p = person(store, email);
  const stamp = new Date().toISOString().slice(0, 10);
  for (const it of items) p.sent[itemKey(it)] = stamp;
  const rec: SendRecord = { at: new Date().toISOString(), count: items.length, channel };
  p.history.unshift(rec);
  p.history = p.history.slice(0, 50);
  if (items.length) p.last = items;
  save(store);
  return rec;
}

/** Full history for one person (newest first) — for an audit view. */
export function history(email: string): SendRecord[] {
  return load()[key(email)]?.history ?? [];
}
