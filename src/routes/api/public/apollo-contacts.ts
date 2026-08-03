/**
 * apollo-contacts.ts — pull the CXOs who actually buy retail planning software,
 * ranked by tier, instead of generic C-level/founder contacts.
 *
 * Accepts POST { company, domain }. Guarded by APOLLO_API_KEY (server-side only).
 * Never throws. Pushes title filtering server-side to Apollo where possible, then
 * ranks tier-1 first and tags each contact with tier + function for the UI.
 */

interface ScanInput {
  company: string;
  domain: string;
  limit?: number;
}

// Tier 1 — economic buyers.
const TIER1_TITLES = [
  "Chief Merchandising Officer", "Chief Merchant", "Chief Supply Chain Officer",
  "COO", "Chief Operating Officer", "CIO", "Chief Information Officer",
  "CTO", "Chief Technology Officer", "Chief Digital Officer",
  "Chief Data Officer", "Chief Analytics Officer", "Chief Data & Analytics Officer",
  "CFO", "Chief Financial Officer",
];

// Tier 2 — functional owners (often the real champion).
const TIER2_TITLES = [
  "VP Merchandise Planning", "SVP Merchandise Planning", "VP Planning & Allocation",
  "VP Demand Planning", "VP Inventory Management", "VP Replenishment",
  "VP Pricing", "VP Promotions", "VP Merchandising", "GMM", "General Merchandise Manager",
  "DMM", "Divisional Merchandise Manager", "VP Retail Technology",
  "VP Enterprise Applications", "VP Data & Analytics", "VP Store Operations",
];

// Tier 3 — directors in those same functions.
const TIER3_TITLES = [
  "Director Merchandise Planning", "Director Planning & Allocation",
  "Director Demand Planning", "Director Inventory", "Director Replenishment",
  "Director Pricing", "Director Merchandising", "Director Retail Technology",
  "Director Data & Analytics",
];

// Titles to exclude even if Apollo returns them.
const EXCLUDE_TERMS = [
  "human resources", "hr", "people", "talent", "legal", "general counsel",
  "communications", "sustainability", "facilities", "brand marketing",
  "advertising", "sales",
];

interface ApolloPerson {
  name?: string;
  first_name?: string;
  last_name?: string;
  title?: string;
  email?: string;
  linkedin_url?: string;
  organization?: { name?: string };
}

export interface Contact {
  name: string;
  title: string;
  email: string | null;
  linkedinUrl: string | null;
  tier: 1 | 2 | 3;
  function: string;
}

function functionFor(title: string): string {
  const t = title.toLowerCase();
  if (/(merchandis|merchant|gmm|dmm|buyer)/.test(t)) return "Merchandising";
  if (/(supply chain|inventory|replenish|allocation|demand)/.test(t)) return "Supply chain";
  if (/(pric|promo|markdown)/.test(t)) return "Pricing";
  if (/(data|analytic|technolog|information|digital|application|cto|cio)/.test(t)) return "Data & technology";
  if (/(financ|cfo)/.test(t)) return "Finance";
  if (/(store|operation|coo)/.test(t)) return "Operations";
  return "Executive";
}

function tierFor(title: string): 1 | 2 | 3 | null {
  const t = title.toLowerCase();
  if (EXCLUDE_TERMS.some((term) => t.includes(term))) return null;
  const has = (list: string[]) => list.some((x) => t.includes(x.toLowerCase()));
  if (has(TIER1_TITLES)) return 1;
  if (has(TIER2_TITLES)) return 2;
  if (has(TIER3_TITLES)) return 3;
  return null;
}

export async function apolloContacts(
  input: ScanInput,
): Promise<{ ok: boolean; contacts: Contact[]; error?: string }> {
  const apiKey = process.env.APOLLO_API_KEY;
  const limit = Math.min(Math.max(input.limit ?? 10, 1), 25);
  try {
    if (!apiKey) {
      return { ok: false, contacts: [], error: "APOLLO_API_KEY is not configured." };
    }
    if (!input.domain) return { ok: false, contacts: [], error: "domain is required" };

    // People Search API (the `mixed_people/search` endpoint is deprecated for API
    // callers; `api_search` is its replacement). Title filtering is pushed
    // server-side via person_titles[], org filtering via q_organization_domains_list[].
    const res = await fetch("https://api.apollo.io/api/v1/mixed_people/api_search", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
        "x-api-key": apiKey,
      },
      body: JSON.stringify({
        q_organization_domains_list: [input.domain],
        person_titles: [...TIER1_TITLES, ...TIER2_TITLES, ...TIER3_TITLES],
        page: 1,
        per_page: 50,
      }),
    });

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return { ok: false, contacts: [], error: `Apollo HTTP ${res.status}: ${body.slice(0, 200)}` };
    }

    const data = (await res.json()) as { people?: ApolloPerson[]; contacts?: ApolloPerson[] };
    const people = data.people ?? data.contacts ?? [];

    const contacts: Contact[] = [];
    for (const p of people) {
      const title = (p.title ?? "").trim();
      if (!title) continue;
      const tier = tierFor(title);
      if (tier == null) continue; // discard excluded / non-ICP titles
      contacts.push({
        name: p.name || `${p.first_name ?? ""} ${p.last_name ?? ""}`.trim(),
        title,
        email: p.email ?? null,
        linkedinUrl: p.linkedin_url ?? null,
        tier,
        function: functionFor(title),
      });
    }

    // Sort tier-1 first, then by function, keeping the existing limit behaviour.
    contacts.sort((a, b) => a.tier - b.tier || a.function.localeCompare(b.function));

    return { ok: true, contacts: contacts.slice(0, limit) };
  } catch (err) {
    return { ok: false, contacts: [], error: (err as Error).message };
  }
}
