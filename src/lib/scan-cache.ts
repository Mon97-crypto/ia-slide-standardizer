/**
 * scan-cache.ts — a client-side 30-day cache for full scan results, keyed by
 * domain. This persists in the browser, so a repeat search of the same company
 * shows the cached result instantly even when the server's own cache was reset
 * (e.g. an ephemeral free-tier filesystem). The user can always Refresh to re-scan.
 */
import type { ScanResult } from "./scan";

const TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days
const KEY = (domain: string) => `ia-scan:v1:${domain.toLowerCase()}`;

export function readScanCache(domain: string): { result: ScanResult; ageMs: number } | null {
  try {
    const raw = localStorage.getItem(KEY(domain));
    if (!raw) return null;
    const { at, result } = JSON.parse(raw) as { at: number; result: ScanResult };
    const ageMs = Date.now() - at;
    if (ageMs > TTL_MS) return null;
    return { result, ageMs };
  } catch {
    return null;
  }
}

export function writeScanCache(domain: string, result: ScanResult): void {
  try {
    localStorage.setItem(KEY(domain), JSON.stringify({ at: Date.now(), result }));
  } catch {
    // storage full/disabled — cache is best-effort.
  }
}
