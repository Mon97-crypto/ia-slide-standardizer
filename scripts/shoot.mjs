import { chromium } from "playwright";

const BASE = process.env.SHOOT_BASE || "http://localhost:8787";
const DOMAIN = "marlowefinch.com";

const S = (name, type, found, detail, weight, contribution, glyph, label, extra = {}) => ({
  name, type, found, detail, weight, score_contribution: contribution, glyph, label,
  evidence: extra.evidence || [], iaProducts: extra.iaProducts || [], soWhat: extra.soWhat || "",
});

// A realistic "Strong buyer" result, pre-sorted the way runScan sorts.
const result = {
  company: "Marlowe & Finch",
  domain: DOMAIN,
  verified: true,
  failedSteps: [],
  cached: false,
  total: 55,
  intent: "Strong buyer",
  signals: [
    S("erp_crm_migration", "positive", true, "Standing up a Snowflake data platform, replacing legacy warehouse.", 20, 20, "▲", "ERP, CRM or platform migration", {
      evidence: [{ title: "Marlowe & Finch selects Snowflake for retail data platform", url: "https://example.com/mf-snowflake", date: "2026-03-11" }],
      iaProducts: ["DataSmart", "ForecastSmart", "InventorySmart"],
      soWhat: "Modern data platform going live now. Lead with time-to-value deploying on top of Snowflake.",
    }),
    S("leadership_change", "positive", true, "Named a new Chief Merchandising Officer in Q1.", 15, 15, "◆", "Leadership change", {
      evidence: [{ title: "Marlowe & Finch appoints Chief Merchandising Officer", url: "https://example.com/mf-cmo", date: "2026-02-02" }],
      iaProducts: ["PlanSmart", "AssortSmart"],
      soWhat: "New merchant re-evaluates the stack early. Lead with a quick assortment win.",
    }),
    S("budget_cuts", "negative", true, "Announced a cost-reduction program citing margin pressure.", 15, -15, "▽", "Budget cuts", {
      evidence: [{ title: "Marlowe & Finch outlines margin recovery plan", url: "https://example.com/mf-margin", date: "2026-01-20" }],
      iaProducts: ["MarkSmart", "PriceSmart"],
      soWhat: "Frame IA as margin recovery, not new spend. Lead with markdown and pricing ROI.",
    }),
    S("ma_activity", "positive", true, "Acquired a regional footwear banner, adding two categories.", 12, 12, "▲", "Mergers and acquisitions", {
      evidence: [{ title: "Marlowe & Finch acquires footwear banner", url: "https://example.com/mf-ma", date: "2026-02-18" }],
      iaProducts: ["PlanSmart", "AssortSmart", "ItemSmart"],
      soWhat: "Integration forces banner consolidation. Lead with one planning hierarchy across banners.",
    }),
    S("operational_pain", "positive", true, "Reported heavy unplanned markdowns and aged inventory.", 10, 10, "◆", "Operational pain", {
      evidence: [{ title: "Marlowe & Finch cites markdown pressure in earnings call", url: "https://example.com/mf-markdowns", date: "2026-03-01" }],
      iaProducts: ["MarkSmart", "InventorySmart", "ForecastSmart"],
      soWhat: "Highest-value signal. Lead with the named markdown pain and quantified ROI.",
    }),
    S("hiring_activity", "positive", true, "Hiring a cluster of demand and merchandise planners.", 8, 8, "▲", "Relevant hiring", {
      evidence: [{ title: "Open roles: Demand Planner, Merchandise Planner", url: "https://example.com/mf-jobs", date: "2026-03-05" }],
      iaProducts: ["PlanSmart", "ForecastSmart"],
      soWhat: "Building a planning team by hand. Lead with automation that lets a smaller team do more.",
    }),
    S("geographic_expansion", "positive", true, "Entering two new regional markets this year.", 5, 5, "▲", "Geographic expansion", {
      evidence: [{ title: "Marlowe & Finch expands into the Southeast", url: "https://example.com/mf-expand", date: "2026-02-25" }],
      iaProducts: ["ForecastSmart", "AssortSmart", "SizeSmart"],
      soWhat: "New geography means demand curves the current model has never seen. Lead with localized forecasting.",
    }),
    S("reorganization", "neutral", false, "Not checked", 55, 0, "○", "Reorganization"),
    S("internal_promotion", "neutral", false, "No confirmed signals found", 45, 0, "○", "Internal promotion"),
    S("bankruptcy", "negative", false, "No bankruptcy filings in the last year.", 45, 0, "▼", "Bankruptcy"),
    S("layoffs", "negative", false, "No confirmed signals found", 25, 0, "▽", "Layoffs or hiring freeze"),
    S("rfp_rfq_rfi", "positive", false, "No confirmed signals found", 25, 0, "◆", "RFP, RFQ or RFI"),
    S("facility_closures", "negative", false, "No confirmed signals found", 10, 0, "▽", "Facility or store closures"),
    S("no_job_openings", "negative", false, "No confirmed signals found", 5, 0, "▽", "No relevant job openings"),
    S("tech_stack_change", "positive", false, "No web technologies detected.", 3, 0, "▲", "Modern tech stack"),
    S("ipo_preparation", "positive", false, "No S-1 registration in the last year.", 2, 0, "▲", "IPO preparation"),
  ],
};

const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
  args: ["--no-sandbox"],
});

async function shoot(name, viewport, fn) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: "networkidle" });
  // Seed the 24h cache so a scan of the demo domain returns instantly.
  await page.evaluate(async (r) => {
    await fetch("/api/public/scan-cache", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ domain: r.domain, company: r.company, result: r }),
    });
  }, result);
  await fn(page);
  await page.screenshot({ path: `scripts/shots/${name}.png`, fullPage: true });
  await ctx.close();
}

const desktop = { width: 1180, height: 900 };
const mobile = { width: 390, height: 900 };

// 1. Empty state / scan form
await shoot("1-empty", desktop, async () => {});

// 2. Results (desktop)
await shoot("2-results", desktop, async (page) => {
  await page.fill('input[placeholder="acme.com"]', DOMAIN);
  await page.click('button[type="submit"]');
  await page.waitForSelector("text=Strong buyer", { timeout: 8000 });
  await page.waitForTimeout(900); // let the spectrum draw
});

// 3. Results with an expanded signal row
await shoot("3-expanded", desktop, async (page) => {
  await page.fill('input[placeholder="acme.com"]', DOMAIN);
  await page.click('button[type="submit"]');
  await page.waitForSelector("text=Strong buyer", { timeout: 8000 });
  await page.click("text=ERP, CRM or platform migration");
  await page.waitForTimeout(500);
});

// 4. Mobile (vertical spectrum)
await shoot("4-mobile", mobile, async (page) => {
  await page.fill('input[placeholder="acme.com"]', DOMAIN);
  await page.click('button[type="submit"]');
  await page.waitForSelector("text=Strong buyer", { timeout: 8000 });
  await page.waitForTimeout(900);
});

await browser.close();
console.log("shots written to scripts/shots/");
