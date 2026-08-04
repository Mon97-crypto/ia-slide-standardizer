/**
 * apollo-contacts.ts — the retail-planning people who actually buy Impact Analytics,
 * ranked by ICP fit. Returns at least ~10 relevant decision-makers (when the company
 * has them) with LinkedIn URLs.
 *
 * Accepts POST { company, domain }. Guarded by APOLLO_API_KEY (server-side only).
 * Query is pushed to Apollo (org domain + ICP titles + decision-maker seniorities);
 * results are then scored for ICP fit, non-ICP functions (HR/legal/marketing/sales/
 * etc.) are dropped, and the best are returned tiered by seniority. Never throws.
 */

interface ScanInput {
  company: string;
  domain: string;
  limit?: number;
}

// ICP role titles pushed to Apollo (fuzzy OR match). Retail planning / merchandising
// / supply-chain / pricing / analytics decision-makers.
const ICP_TITLES = [
  "Chief Merchandising Officer", "Chief Merchant", "Chief Supply Chain Officer",
  "Chief Operating Officer", "Chief Information Officer", "Chief Technology Officer",
  "Chief Digital Officer", "Chief Data Officer", "Chief Analytics Officer", "Chief Financial Officer",
  "SVP Merchandising", "VP Merchandising", "VP Merchandise Planning", "VP Planning and Allocation",
  "VP Demand Planning", "VP Inventory", "VP Replenishment", "VP Pricing", "VP Promotions",
  "VP Supply Chain", "VP Retail Technology", "VP Data and Analytics", "VP Store Operations",
  "General Merchandise Manager", "Divisional Merchandise Manager",
  "Head of Merchandise Planning", "Head of Allocation", "Head of Demand Planning",
  "Director Merchandise Planning", "Director Planning and Allocation", "Director Demand Planning",
  "Director Inventory", "Director Replenishment", "Director Pricing", "Director Merchandising",
  "Director Supply Chain", "Director Retail Technology", "Director Data and Analytics",
  "Merchandise Planner", "Demand Planner", "Allocation Analyst", "Inventory Planner",
  "Pricing Manager", "Category Manager", "Buyer",
];

// Apollo seniorities that bias toward decision-makers.
const SENIORITIES = ["c_suite", "vp", "head", "director", "manager"];

// ── ICP scoring on the returned people ──────────────────────────────────────────
const CORE = [/merchandis/, /\bmerchant\b/, /\bplanner\b/, /\bplanning\b/, /allocat/, /replenish/, /inventor/, /\bdemand\b/, /assortment/, /\bbuyer\b/, /\bbuying\b/, /\bpric/, /promotion/, /markdown/, /supply chain/, /category manage/, /space plan/, /\bgmm\b/, /\bdmm\b/];
const ADJACENT = [/\bdata\b/, /analytic/, /business intelligence/, /forecast/, /\bdigital\b/, /e-?commerce/, /retail tech/, /\boperations?\b/, /\bfinance\b/, /\bcfo\b/, /information officer/, /\bcio\b/, /\bcto\b/, /technolog/];
const REJECT = [/human resource/, /\bhr\b/, /\bpeople\b/, /talent/, /recruit/, /\blegal\b/, /counsel/, /communicat/, /public relations/, /\bmarketing\b/, /\bbrand\b/, /advertis/, /social media/, /sustainab/, /facilit/, /\bsales\b/, /store associate/, /cashier/, /warehouse/, /\bsecurity\b/, /customer service/, /software engineer/, /account executive/];

function icpScore(title: string): number {
  const t = title.toLowerCase();
  if (REJECT.some((r) => r.test(t))) return -1;
  if (CORE.some((r) => r.test(t))) return 3;
  if (ADJACENT.some((r) => r.test(t))) return 1.5;
  return 0;
}

function seniorityTier(title: string): 1 | 2 | 3 {
  const t = title.toLowerCase();
  if (/\bchief\b|\bceo\b|\bcoo\b|\bcfo\b|\bcio\b|\bcto\b|\bcdo\b|\bcao\b|\bevp\b|executive vice president|\bpresident\b|\bfounder\b|\bowner\b/.test(t)) return 1;
  if (/\bsvp\b|senior vice president|\bvp\b|vice president|head of|\bgmm\b|general merchandise manager|\bdmm\b|divisional merchandise manager/.test(t)) return 2;
  return 3;
}

function functionFor(title: string): string {
  const t = title.toLowerCase();
  if (/(merchandis|merchant|gmm|dmm|buyer|buying|assortment)/.test(t)) return "Merchandising";
  if (/(supply chain|inventory|replenish|allocation|demand|planner|planning)/.test(t)) return "Planning & supply chain";
  if (/(pric|promo|markdown)/.test(t)) return "Pricing";
  if (/(data|analytic|technolog|information|digital|application|cto|cio|forecast)/.test(t)) return "Data & technology";
  if (/(financ|cfo)/.test(t)) return "Finance";
  if (/(store|operation|coo)/.test(t)) return "Operations";
  return "Executive";
}

interface ApolloPerson {
  name?: string;
  first_name?: string;
  last_name?: string;
  title?: string;
  email?: string;
  linkedin_url?: string;
}

export interface Contact {
  name: string;
  title: string;
  email: string | null;
  linkedinUrl: string | null;
  tier: 1 | 2 | 3;
  function: string;
}

export async function apolloContacts(
  input: ScanInput,
): Promise<{ ok: boolean; contacts: Contact[]; error?: string }> {
  const apiKey = process.env.APOLLO_API_KEY;
  const limit = Math.min(Math.max(input.limit ?? 15, 1), 25);
  try {
    if (!apiKey) return { ok: false, contacts: [], error: "APOLLO_API_KEY is not configured." };
    if (!input.domain) return { ok: false, contacts: [], error: "domain is required" };

    const res = await fetch("https://api.apollo.io/api/v1/mixed_people/api_search", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json", "x-api-key": apiKey },
      body: JSON.stringify({
        q_organization_domains_list: [input.domain],
        person_titles: ICP_TITLES,
        person_seniorities: SENIORITIES,
        page: 1,
        per_page: 100,
      }),
    });

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return { ok: false, contacts: [], error: `Apollo HTTP ${res.status}: ${body.slice(0, 200)}` };
    }

    const data = (await res.json()) as { people?: ApolloPerson[]; contacts?: ApolloPerson[] };
    const people = data.people ?? data.contacts ?? [];

    // Score every person for ICP fit; keep the relevant ones.
    const scored = people
      .map((p) => {
        const title = (p.title ?? "").trim();
        return { p, title, score: title ? icpScore(title) : -1 };
      })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score || seniorityTier(a.title) - seniorityTier(b.title));

    const contacts: Contact[] = scored.slice(0, limit).map(({ p, title }) => ({
      name: p.name || `${p.first_name ?? ""} ${p.last_name ?? ""}`.trim(),
      title,
      email: p.email ?? null,
      linkedinUrl: p.linkedin_url ?? null,
      tier: seniorityTier(title),
      function: functionFor(title),
    }));

    // Final display order: tier first, then ICP score already applied within.
    contacts.sort((a, b) => a.tier - b.tier);

    return { ok: true, contacts };
  } catch (err) {
    return { ok: false, contacts: [], error: (err as Error).message };
  }
}
