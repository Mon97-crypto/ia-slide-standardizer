/**
 * _sec.ts — shared SEC access. The SEC rejects requests without a descriptive
 * User-Agent and rate-limits above 10 req/s, so every SEC request goes through
 * secFetch, which sets the UA and spaces requests at least 120ms apart GLOBALLY
 * (the bulk queue relies on this spacing being process-wide, not per-scan).
 */

const SEC_USER_AGENT =
  process.env.SEC_USER_AGENT ||
  "ImpactAnalytics-AccountScanner research@impactanalytics.ai";

const MIN_GAP_MS = 120;
let lastCallAt = 0;
let chain: Promise<void> = Promise.resolve();

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** Serialize SEC calls so they never fire closer than MIN_GAP_MS apart. */
export async function secFetch(url: string): Promise<Response> {
  // Each call waits its turn in a global chain, then enforces the gap.
  const run = chain.then(async () => {
    const now = Date.now();
    const wait = Math.max(0, MIN_GAP_MS - (now - lastCallAt));
    if (wait > 0) await sleep(wait);
    lastCallAt = Date.now();
  });
  chain = run.catch(() => {});
  await run;

  return fetch(url, {
    headers: {
      "User-Agent": SEC_USER_AGENT,
      Accept: "application/json",
      "Accept-Encoding": "gzip, deflate",
    },
  });
}

export function padCik(cik: string | number): string {
  return String(cik).replace(/^0+/, "").padStart(10, "0");
}
