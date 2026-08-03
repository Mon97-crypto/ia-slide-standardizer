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

export interface SearchProvider {
  name: string;
  available: boolean;
  search: (query: string, num?: number) => Promise<Hit[]>;
}

async function fetchJson(url: string, timeoutMs = 12_000): Promise<unknown | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function serpApi(key: string): SearchProvider {
  return {
    name: "serpapi",
    available: true,
    async search(query, num = 8) {
      const url =
        `https://serpapi.com/search.json?engine=google&num=${num}` +
        `&q=${encodeURIComponent(query)}&api_key=${encodeURIComponent(key)}`;
      const data = (await fetchJson(url)) as { organic_results?: Array<Record<string, unknown>> } | null;
      const rows = data?.organic_results ?? [];
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
  return {
    name: "google_cse",
    available: true,
    async search(query, num = 8) {
      const url =
        `https://www.googleapis.com/customsearch/v1?key=${encodeURIComponent(key)}` +
        `&cx=${encodeURIComponent(cx)}&num=${Math.min(num, 10)}&q=${encodeURIComponent(query)}`;
      const data = (await fetchJson(url)) as { items?: Array<Record<string, unknown>> } | null;
      const rows = data?.items ?? [];
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
