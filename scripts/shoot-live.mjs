import { chromium } from "playwright";

const BASE = "http://localhost:8787";
const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
  args: ["--no-sandbox"],
});
const ctx = await browser.newContext({ viewport: { width: 1180, height: 1000 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto(BASE, { waitUntil: "networkidle" });
const DOMAIN = process.env.DOMAIN || "marlowefinch.com";
const COMPANY = process.env.COMPANY || "Marlowe & Finch";
await page.fill('input[placeholder="acme.com"]', DOMAIN);
await page.fill('input[placeholder="Acme Retail"]', COMPANY);
await page.click('button[type="submit"]');
// Real scan: techstack/edgar hit the firewall and fail open (~up to 10s); news is
// served from the local mock. Wait for the results to land.
await page.waitForSelector("text=/Strong buyer|Potential buyer|Neutral|Poor fit|Disqualified/", { timeout: 150000 });
await page.waitForTimeout(1200); // spectrum draw + row stagger
const tag = process.env.TAG || "live";
await page.screenshot({ path: `scripts/shots/${tag}-results.png`, fullPage: true });
// Expand the first found signal row to show its grounded evidence.
await page.click("text=Leadership change").catch(() => {});
await page.waitForTimeout(500);
await page.screenshot({ path: `scripts/shots/${tag}-expanded.png`, fullPage: true });
await browser.close();
console.log("live shots written");
