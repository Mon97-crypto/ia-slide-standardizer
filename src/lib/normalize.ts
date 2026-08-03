/**
 * normalize.ts — accept a bare domain, a full URL, or a pasted URL with tracking
 * parameters, and normalize silently. Never make someone fix a URL by hand.
 */

export interface NormalizedTarget {
  /** Bare hostname, no scheme, no www, no path. e.g. "fila.com" */
  domain: string;
  /** A best-guess company name derived from the domain slug, title cased. */
  companyGuess: string;
}

export function normalizeDomain(raw: string): string {
  let value = (raw || "").trim().toLowerCase();
  if (!value) return "";
  // Strip a scheme if present, otherwise add one so URL() can parse it.
  if (!/^[a-z][a-z0-9+.-]*:\/\//.test(value)) {
    value = `https://${value}`;
  }
  try {
    const url = new URL(value);
    let host = url.hostname;
    if (host.startsWith("www.")) host = host.slice(4);
    return host;
  } catch {
    // Fall back to a rough strip if URL parsing fails.
    return value
      .replace(/^[a-z]+:\/\//, "")
      .replace(/^www\./, "")
      .split("/")[0]
      .split("?")[0]
      .trim();
  }
}

/** Turn "fila.com" into "Fila", "acme-retail.co.uk" into "Acme Retail". */
export function companyFromDomain(domain: string): string {
  const slug = domain
    .replace(/^www\./, "")
    // drop the public suffix (last one or two labels).
    .replace(/\.(com|net|org|io|co|ai|app|shop|store|us|uk|ca|au|de|fr|jp|in)(\.[a-z]{2})?$/, "")
    .split(".")
    .pop() ?? domain;
  return slug
    .split(/[-_]/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function normalizeTarget(raw: string): NormalizedTarget {
  const domain = normalizeDomain(raw);
  return { domain, companyGuess: companyFromDomain(domain) };
}
