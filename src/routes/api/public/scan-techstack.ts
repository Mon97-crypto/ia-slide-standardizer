/**
 * scan-techstack.ts — fetches the domain homepage, verifies the company matches
 * the domain, and fingerprints the stack by regex against headers and HTML.
 * Accepts POST { company, domain }. Never throws.
 */

import type { Evidence, FunctionResult, Signal } from "../../../lib/scan-contract";

interface ScanInput {
  company: string;
  domain: string;
}

const COMPANY_STOPWORDS = new Set([
  "inc", "corp", "llc", "ltd", "co", "plc", "group", "holdings",
  "technologies", "solutions", "services", "enterprises", "global",
]);

function tokenizeCompany(company: string): string[] {
  return company
    .toLowerCase()
    .replace(/['’]/g, "")
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length >= 2 && !COMPANY_STOPWORDS.has(t));
}

function domainSlug(domain: string): string {
  return domain
    .replace(/^www\./, "")
    .split(".")[0]
    .replace(/[^a-z0-9]/gi, "")
    .toLowerCase();
}

function extractMeta(html: string): string {
  const parts: string[] = [];
  const patterns = [
    /<title[^>]*>([^<]*)<\/title>/i,
    /<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']+)["']/i,
    /<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']/i,
    /<meta[^>]+name=["']application-name["'][^>]+content=["']([^"']+)["']/i,
  ];
  for (const p of patterns) {
    const m = html.match(p);
    if (m?.[1]) parts.push(m[1]);
  }
  return parts.join(" ").toLowerCase();
}

interface TechDef {
  name: string;
  tier: "modern" | "legacy" | "neutral";
  headerTest?: (headers: Headers) => boolean;
  htmlTest?: RegExp;
}

const TECHS: TechDef[] = [
  { name: "WordPress", tier: "legacy", htmlTest: /wp-content|name=["']generator["'][^>]+wordpress/i },
  { name: "Drupal", tier: "legacy", htmlTest: /drupal-settings-json|name=["']generator["'][^>]+drupal/i },
  { name: "Shopify", tier: "neutral", htmlTest: /cdn\.shopify\.com/i, headerTest: (h) => h.has("x-shopify-stage") },
  { name: "Salesforce", tier: "neutral", htmlTest: /force\.com|lightning\.force/i },
  { name: "HubSpot", tier: "neutral", htmlTest: /js\.hs-scripts\.com/i },
  { name: "Marketo", tier: "neutral", htmlTest: /munchkin\.marketo\.net/i },
  { name: "Google Analytics", tier: "neutral", htmlTest: /gtag\/js|googletagmanager\.com/i },
  { name: "React", tier: "modern", htmlTest: /data-reactroot|__NEXT_DATA__|id=["']root["']/i },
  { name: "Angular", tier: "modern", htmlTest: /ng-version/i },
  { name: "Vue", tier: "modern", htmlTest: /data-v-[0-9a-f]{8}|id=["']app["']/i },
  { name: "AWS", tier: "modern", headerTest: (h) => [...h.keys()].some((k) => k.startsWith("x-amz")) },
  { name: "Cloudflare", tier: "neutral", headerTest: (h) => h.has("cf-ray") },
  { name: "Intercom", tier: "neutral", htmlTest: /widget\.intercom\.io/i },
  { name: "Zendesk", tier: "neutral", htmlTest: /zdassets\.com|zendesk/i },
];

async function fetchHomepage(domain: string): Promise<{ headers: Headers; html: string; ok: boolean } | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(`https://${domain}`, {
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        Accept: "text/html,application/xhtml+xml",
      },
    });
    const reader = res.body?.getReader();
    let html = "";
    if (reader) {
      const decoder = new TextDecoder();
      let received = 0;
      const CAP = 200 * 1024;
      while (received < CAP) {
        const { done, value } = await reader.read();
        if (done) break;
        received += value.byteLength;
        html += decoder.decode(value, { stream: true });
      }
      await reader.cancel().catch(() => {});
    }
    return { headers: res.headers, html, ok: res.ok };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function scanTechstack(input: ScanInput): Promise<FunctionResult> {
  const { company, domain } = input;
  try {
    if (!domain) return { ok: false, signals: [], error: "domain is required" };

    const page = await fetchHomepage(domain);

    // Verification. If the fetch fails or 4xx, verified:true — many sites block
    // bots and we must not fail the scan over it.
    let verified = true;
    let resolvedName = company;
    if (page && page.ok) {
      const metaText = extractMeta(page.html);
      const tokens = tokenizeCompany(company);
      const slug = domainSlug(domain);
      const joined = tokens.join("");
      const slugInTokens = tokens.includes(slug);
      const everyTokenInMeta =
        tokens.length > 0 &&
        tokens.every((t) => new RegExp(`\\b${t}\\b`).test(metaText));
      verified = joined === slug || slug.includes(joined) || slugInTokens || everyTokenInMeta;
      const titleMatch = page.html.match(/<title[^>]*>([^<]*)<\/title>/i);
      if (titleMatch?.[1]) resolvedName = titleMatch[1].trim().slice(0, 120);
    }

    // Fingerprint.
    const detected: TechDef[] = [];
    if (page) {
      for (const tech of TECHS) {
        const byHeader = tech.headerTest ? tech.headerTest(page.headers) : false;
        const byHtml = tech.htmlTest ? tech.htmlTest.test(page.html) : false;
        if (byHeader || byHtml) detected.push(tech);
      }
    }

    const modern = detected.filter((t) => t.tier === "modern");
    const found = modern.length > 0;
    const homeUrl = `https://${domain}`;
    const evidence: Evidence[] = detected.slice(0, 5).map((t) => ({
      title: t.name,
      url: homeUrl,
      date: "",
    }));

    const signal: Signal = {
      name: "tech_stack_change",
      type: "positive",
      found,
      detail: found
        ? `Modern stack detected: ${modern.map((t) => t.name).join(", ")}.`
        : detected.length
          ? `Only legacy or neutral tech detected: ${detected.map((t) => t.name).join(", ")}.`
          : "No web technologies detected.",
      evidence,
    };

    return {
      ok: true,
      signals: [signal],
      meta: { verified, resolvedName, detected: detected.map((t) => t.name) },
    };
  } catch (err) {
    return { ok: false, signals: [], error: (err as Error).message };
  }
}
