/**
 * mock-serpapi.mjs — a local stand-in for serpapi.com that returns real
 * SerpAPI-shaped JSON, so the actual search-provider + classifier pipeline can
 * be exercised end to end without reaching the (firewalled) live API. Switches
 * on the query the provider sends, exactly as the real API would key off `q`.
 *
 * Run: node scripts/mock-serpapi.mjs   (listens on :8899)
 * Point the app at it: SERPAPI_KEY=demo SERPAPI_BASE_URL=http://localhost:8899
 */
import { createServer } from "node:http";

const org = (title, url, date, snippet) => ({ title, link: url, date, snippet });

// Each entry: match a distinctive term in the query → grounded organic_results.
const ORGANIC = [
  {
    match: ["chief merchandising", "appoints", "vp planning"],
    results: [
      org(
        "Marlowe & Finch appoints new Chief Merchandising Officer",
        "https://retaildive.com/marlowe-cmo",
        "2026-02-02",
        "Marlowe & Finch names a new Chief Merchandising Officer to lead assortment and planning.",
      ),
    ],
  },
  {
    match: ["snowflake", "s/4hana", "databricks"],
    results: [
      org(
        "Marlowe & Finch selects Snowflake for its retail data platform",
        "https://businesswire.com/marlowe-snowflake",
        "2026-03-11",
        "The retailer is standing up a modern data platform, selecting Snowflake to replace a legacy warehouse.",
      ),
    ],
  },
  {
    match: ["stockout", "markdown", "sell-through", "forecast accuracy"],
    results: [
      org(
        "Marlowe & Finch cites heavy markdowns in Q4 results",
        "https://wwd.com/marlowe-markdowns",
        "2026-03-01",
        "Marlowe & Finch reported heavy unplanned markdowns and aged inventory pressuring gross margin.",
      ),
    ],
  },
  {
    match: ["new stores", "distribution center", "expands into"],
    results: [
      org(
        "Marlowe & Finch expands into the Southeast",
        "https://chainstoreage.com/marlowe-expansion",
        "2026-02-25",
        "Marlowe & Finch expands into the Southeast with new stores and a new distribution center.",
      ),
    ],
  },
  {
    match: ["cost reduction", "capex", "margin pressure"],
    results: [
      org(
        "Marlowe & Finch outlines cost reduction program",
        "https://reuters.com/marlowe-cost",
        "2026-01-20",
        "Marlowe & Finch announced a cost reduction program citing margin pressure across categories.",
      ),
    ],
  },
  {
    match: ["rfp", "rfi", "rfq"],
    results: [
      org(
        "Marlowe & Finch issues RFP for merchandise planning",
        "https://govwin.com/marlowe-rfp",
        "2026-03-08",
        "Marlowe & Finch issued an RFP for merchandise planning and markdown optimization software.",
      ),
    ],
  },
  // Deliberately no hits for closures / layoffs / promotion → those stay found:false.
];

const JOBS = [
  {
    title: "Demand Planner, Womenswear",
    share_link: "https://www.google.com/search?q=marlowe+demand+planner",
    detected_extensions: { posted_at: "3 days ago" },
    description:
      "Marlowe & Finch seeks a Demand Planner to own forecasting and replenishment. Experience with Blue Yonder a plus.",
  },
  {
    title: "Merchandise Planner",
    share_link: "https://www.google.com/search?q=marlowe+merchandise+planner",
    detected_extensions: { posted_at: "1 week ago" },
    description: "Merchandise Planner to manage open-to-buy and assortment planning across banners.",
  },
  {
    title: "Allocation Analyst",
    share_link: "https://www.google.com/search?q=marlowe+allocation+analyst",
    detected_extensions: { posted_at: "5 days ago" },
    description: "Allocation Analyst supporting store-level inventory allocation and replenishment.",
  },
];

function organicFor(q) {
  const ql = q.toLowerCase();
  for (const entry of ORGANIC) {
    if (entry.match.some((m) => ql.includes(m))) return entry.results;
  }
  return [];
}

const server = createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  const engine = url.searchParams.get("engine");
  const q = url.searchParams.get("q") || "";
  res.setHeader("content-type", "application/json");
  if (engine === "google_jobs") {
    res.end(JSON.stringify({ jobs_results: JOBS }));
  } else {
    res.end(JSON.stringify({ organic_results: organicFor(q) }));
  }
});

server.listen(8899, () => console.log("mock serpapi on :8899"));
