import { chromium } from "playwright";

const BASE = process.env.SHOOT_BASE || "http://localhost:8787";
const DOMAIN = "marlowefinch.com";

// Catalog mirror (label, glyph, weight, group, type) — keep in sync with scan-contract.ts.
const CAT = {
  tech_stack_change: ["Current tech stack", "▲", 5, "key", "positive"],
  rfp_rfq_rfi: ["RFP, RFQ or RFI", "◆", 25, "key", "positive"],
  ma_activity: ["M&A activity", "▲", 15, "key", "positive"],
  geographic_expansion: ["Geographic expansion", "▲", 10, "key", "positive"],
  operational_pain: ["Operational pain", "◆", 25, "key", "positive"],
  leadership_change: ["Leadership changes", "◆", 15, "key", "positive"],
  erp_crm_migration: ["ERP, CRM or cloud migration", "▲", 20, "key", "positive"],
  bankruptcy: ["Bankruptcy", "▼", 45, "key", "negative"],
  store_expansion: ["Stores / facility expansion", "▲", 10, "key", "positive"],
  vendor_sentiment: ["Current vendor sentiment", "◆", 22, "key", "positive"],
  new_product_line: ["New product line", "▲", 6, "supporting", "positive"],
  hiring_activity: ["Relevant hiring", "▲", 8, "supporting", "positive"],
  layoffs: ["Layoffs / hiring freeze", "▽", 15, "supporting", "negative"],
  budget_cuts: ["Budget cuts", "▽", 12, "supporting", "negative"],
  facility_closures: ["Facility / store closures", "▽", 10, "supporting", "negative"],
  procurement_freeze: ["Procurement freeze", "▽", 5, "supporting", "negative"],
  debt_restructuring: ["Debt restructuring", "▲", 6, "supporting", "positive"],
  banner_selloff: ["Brand / banner sell-off", "▲", 6, "supporting", "positive"],
  rival_tool_purchase: ["Recent rival tool purchase", "◆", 12, "supporting", "positive"],
};

// Found signals with realistic evidence/soWhat; everything else renders "not found".
const FOUND = {
  operational_pain: {
    detail: "Reported heavy unplanned markdowns and aged inventory on the Q1 earnings call.",
    evidence: [{ title: "Marlowe & Finch cites markdown pressure in earnings call", url: "https://example.com/mf-markdowns", date: "2026-03-01" }],
    iaProducts: ["MarkSmart", "InventorySmart", "ForecastSmart"],
    soWhat: "Highest-value signal. Lead with the named markdown pain and quantified ROI.",
  },
  erp_crm_migration: {
    detail: "Standing up a Snowflake data platform, replacing a legacy warehouse.",
    evidence: [{ title: "Marlowe & Finch selects Snowflake for retail data platform", url: "https://example.com/mf-snowflake", date: "2026-03-11" }],
    iaProducts: ["DataSmart", "ForecastSmart", "InventorySmart"],
    soWhat: "Modern data platform going live now. Lead with time-to-value on top of Snowflake.",
  },
  leadership_change: {
    detail: "Named a new Chief Merchandising Officer in Q1.",
    evidence: [{ title: "Marlowe & Finch appoints Chief Merchandising Officer", url: "https://example.com/mf-cmo", date: "2026-02-02" }],
    iaProducts: ["PlanSmart", "AssortSmart"],
    soWhat: "New merchant re-evaluates the stack early. Lead with a quick assortment win.",
  },
  geographic_expansion: {
    detail: "Entering two new regional markets this year.",
    evidence: [{ title: "Marlowe & Finch expands into the Southeast", url: "https://example.com/mf-expand", date: "2026-02-25" }],
    iaProducts: ["ForecastSmart", "AssortSmart", "SizeSmart"],
    soWhat: "New geography means demand curves the current model has never seen. Lead with localized forecasting.",
  },
  hiring_activity: {
    detail: "Hiring a cluster of demand and merchandise planners.",
    evidence: [{ title: "Open roles: Demand Planner, Merchandise Planner", url: "https://example.com/mf-jobs", date: "2026-03-05" }],
    iaProducts: ["PlanSmart", "ForecastSmart"],
    soWhat: "Building a planning team by hand. Lead with automation that lets a smaller team do more.",
  },
  budget_cuts: {
    detail: "Announced a cost-reduction program citing margin pressure.",
    evidence: [{ title: "Marlowe & Finch outlines margin recovery plan", url: "https://example.com/mf-margin", date: "2026-01-20" }],
    iaProducts: ["MarkSmart", "PriceSmart"],
    soWhat: "Frame IA as margin recovery, not new spend. Lead with markdown and pricing ROI.",
  },
};

const signals = Object.entries(CAT).map(([name, [label, glyph, weight, group, type]]) => {
  const f = FOUND[name];
  const found = Boolean(f);
  const contribution = found ? (type === "negative" ? -weight : type === "positive" ? weight : 0) : 0;
  return {
    name, type, found, weight, glyph, label, group,
    detail: f?.detail ?? "No confirmed signals found.",
    evidence: f?.evidence ?? [],
    iaProducts: f?.iaProducts ?? [],
    soWhat: f?.soWhat ?? "",
    score_contribution: contribution,
  };
});

const total = signals.reduce((s, x) => s + x.score_contribution, 0);
const result = {
  company: "Marlowe & Finch",
  domain: DOMAIN,
  verified: true,
  failedSteps: [],
  cached: false,
  total,
  intent: total >= 30 ? "Strong buyer" : total >= 10 ? "Potential buyer" : "Neutral",
  signals,
};

const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
  args: ["--no-sandbox"],
});

// A rich account so the Account Information section renders fully. logoUrl points
// at a locally-served asset so the tile shows an image without external egress.
const account = {
  name: "Marlowe & Finch",
  domain: DOMAIN,
  industry: "Retail Apparel & Fashion",
  revenue: "$1.2B",
  hq: "New York, New York, United States",
  website: `https://${DOMAIN}`,
  logoUrl: "/ia_logo.png",
  employees: "4,200",
  description: "Marlowe & Finch is a specialty apparel and footwear retailer operating 320 stores across North America.",
};

async function shoot(name, viewport, fn) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: "networkidle" });
  // Seed the cache + account so a scan of the demo domain returns instantly.
  await page.evaluate(async ({ r, a }) => {
    await fetch("/api/public/scan-cache", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ domain: r.domain, company: r.company, result: r }),
    });
    localStorage.setItem(`ia-account:${a.domain}`, JSON.stringify({ at: Date.now(), account: a }));
  }, { r: result, a: account });
  await fn(page);
  await page.screenshot({ path: `scripts/shots/${name}.png`, fullPage: true });
  await ctx.close();
}

const desktop = { width: 1180, height: 900 };
const mobile = { width: 390, height: 900 };

// 1. Empty state / scan form
await shoot("1-empty", desktop, async () => {});

// 2. Results dashboard (desktop)
await shoot("2-results", desktop, async (page) => {
  await page.fill('input[placeholder="acme.com"]', DOMAIN);
  await page.click('button[type="submit"]');
  await page.waitForSelector("text=Strong buyer", { timeout: 8000 });
  await page.waitForTimeout(900);
});

// 3. Results with an expanded signal row
await shoot("3-expanded", desktop, async (page) => {
  await page.fill('input[placeholder="acme.com"]', DOMAIN);
  await page.click('button[type="submit"]');
  await page.waitForSelector("text=Strong buyer", { timeout: 8000 });
  await page.click("text=Operational pain");
  await page.waitForTimeout(500);
});

// 4. Mobile
await shoot("4-mobile", mobile, async (page) => {
  await page.fill('input[placeholder="acme.com"]', DOMAIN);
  await page.click('button[type="submit"]');
  await page.waitForSelector("text=Strong buyer", { timeout: 8000 });
  await page.waitForTimeout(900);
});

await browser.close();
console.log("shots written to scripts/shots/");
