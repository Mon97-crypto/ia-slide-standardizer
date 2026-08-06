/**
 * search-provider.ts — a dedicated web-search source. Supports two backends,
 * selected by whichever key is present:
 *   - SerpAPI       (SERPAPI_KEY)
 *   - Google CSE    (GOOGLE_CSE_KEY + GOOGLE_CSE_CX)
 *
 * Returns grounded hits (real title / url / date / snippet). Never throws.
 */

export interface Hit {
  title: string;
  url: string;
  date: string;
  snippet: string;
}

/** Provider-instance state so callers can tell a rate/quota failure apart from a
 * genuinely empty result set (a fresh object is created per getSearchProvider). */
export interface ProviderState {
  /** A search hit a rate-limit or quota/auth error (HTTP 429/401/403). */
  limited: boolean;
  /** A search hit a server/network error (HTTP 5xx / timeout). */
  errored: boolean;
}

export interface SearchProvider {
  name: string;
  available: boolean;
  state?: ProviderState;
  /** recentOnly restricts results to roughly the last 12 months. */
  search: (query: string, num?: number, recentOnly?: boolean) => Promise<Hit[]>;
}

interface FetchResult {
  status: number; // 200 ok, 0 = network/timeout, else HTTP status
  data: unknown | null;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Fetch JSON, retrying transient rate-limits (429) and server blips (503) with
// exponential backoff so a burst of concurrent searches (bulk runs) doesn't turn
// into silent empty results.
async function fetchJson(url: string, timeoutMs = 12_000): Promise<FetchResult> {
  for (let attempt = 0; attempt < 3; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal });
      if (res.ok) return { status: 200, data: await res.json() };
      if ((res.status === 429 || res.status === 503) && attempt < 2) {
        clearTimeout(timer);
        await sleep(1200 * (attempt + 1)); // 1.2s, 2.4s
        continue;
      }
      return { status: res.status, data: null };
    } catch {
      if (attempt < 2) {
        clearTimeout(timer);
        await sleep(800 * (attempt + 1));
        continue;
      }
      return { status: 0, data: null };
    } finally {
      clearTimeout(timer);
    }
  }
  return { status: 0, data: null };
}

function serpApi(key: string): SearchProvider {
  const base = process.env.SERPAPI_BASE_URL || "https://serpapi.com";
  const state: ProviderState = { limited: false, errored: false };
  return {
    name: "serpapi",
    available: true,
    state,
    async search(query, num = 8, recentOnly = false) {
      const recency = recentOnly ? "&tbs=qdr:y" : ""; // Google "past year" filter
      const url =
        `${base}/search.json?engine=google&num=${num}${recency}` +
        `&q=${encodeURIComponent(query)}&api_key=${encodeURIComponent(key)}`;
      const { status, data } = await fetchJson(url);
      if (status === 429 || status === 401 || status === 403) state.limited = true;
      else if (status === 0 || status >= 500) state.errored = true;
      const rows = (data as { organic_results?: Array<Record<string, unknown>> } | null)?.organic_results ?? [];
      return rows
        .map((r) => ({
          title: String(r.title ?? ""),
          url: String(r.link ?? ""),
          date: String(r.date ?? ""),
          snippet: String(r.snippet ?? ""),
        }))
        .filter((h) => h.url);
    },
  };
}

function googleCse(key: string, cx: string): SearchProvider {
  const state: ProviderState = { limited: false, errored: false };
  return {
    name: "google_cse",
    available: true,
    state,
    async search(query, num = 8, recentOnly = false) {
      const recency = recentOnly ? "&dateRestrict=m12" : ""; // last 12 months
      const url =
        `https://www.googleapis.com/customsearch/v1?key=${encodeURIComponent(key)}` +
        `&cx=${encodeURIComponent(cx)}&num=${Math.min(num, 10)}${recency}&q=${encodeURIComponent(query)}`;
      const { status, data } = await fetchJson(url);
      if (status === 429 || status === 401 || status === 403) state.limited = true;
      else if (status === 0 || status >= 500) state.errored = true;
      const rows = (data as { items?: Array<Record<string, unknown>> } | null)?.items ?? [];
      return rows
        .map((r) => {
          const pagemap = (r.pagemap ?? {}) as { metatags?: Array<Record<string, string>> };
          const meta = pagemap.metatags?.[0] ?? {};
          return {
            title: String(r.title ?? ""),
            url: String(r.link ?? ""),
            date: String(meta["article:published_time"] ?? meta["date"] ?? ""),
            snippet: String(r.snippet ?? ""),
          };
        })
        .filter((h) => h.url);
    },
  };
}

const NOOP: SearchProvider = {
  name: "none",
  available: false,
  async search() {
    return [];
  },
};

/** Pick a backend from the environment. SerpAPI wins if both are configured. */
export function getSearchProvider(): SearchProvider {
  if (process.env.SERPAPI_KEY) return serpApi(process.env.SERPAPI_KEY);
  if (process.env.GOOGLE_CSE_KEY && process.env.GOOGLE_CSE_CX) {
    return googleCse(process.env.GOOGLE_CSE_KEY, process.env.GOOGLE_CSE_CX);
  }
  return NOOP;
}
