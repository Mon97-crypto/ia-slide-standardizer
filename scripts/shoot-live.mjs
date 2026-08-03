import { chromium } from "playwright";

const BASE = "http://localhost:8787";
const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
  args: ["--no-sandbox"],
});
const ctx = await browser.newContext({ viewport: { width: 1180, height: 1000 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto(BASE, { waitUntil: "networkidle" });
await page.fill('input[placeholder="acme.com"]', "marlowefinch.com");
await page.fill('input[placeholder="Acme Retail"]', "Marlowe & Finch");
await page.click('button[type="submit"]');
// Real scan: techstack/edgar hit the firewall and fail open (~up to 10s); news is
// served from the local mock. Wait for the results to land.
await page.waitForSelector("text=/Strong buyer|Potential buyer|Neutral|Poor fit/", { timeout: 30000 });
await page.waitForTimeout(1200); // spectrum draw + row stagger
await page.screenshot({ path: "scripts/shots/live-results.png", fullPage: true });
// Expand the ERP row to show grounded evidence from the (mocked) search source.
await page.click("text=ERP, CRM or platform migration");
await page.waitForTimeout(500);
await page.screenshot({ path: "scripts/shots/live-expanded.png", fullPage: true });
await browser.close();
console.log("live shots written");
