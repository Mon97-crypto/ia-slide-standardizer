/**
 * report.ts — build a printable, word-for-word report of a scan result and open
 * the browser's print dialog (Save as PDF). No external dependency: it renders an
 * HTML document into a hidden iframe and calls print(), so the PDF contains the
 * exact scan text — account info, every detected signal with its detail, evidence
 * links, "so what" and IA products, and the undetected list.
 */
import type { ScanResult, ScoredSignal } from "./scan";
import type { AccountInfo } from "./account";

function esc(s: string): string {
  return (s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
}

const CATEGORY: Record<string, string> = { positive: "Positive", negative: "Negative", neutral: "Mixed" };

function signalBlock(s: ScoredSignal): string {
  const evidence = (s.evidence ?? [])
    .map((e) => `<li><a href="${esc(e.url)}">${esc(e.title || e.url)}</a>${e.date ? ` <span class="date">— ${esc(e.date)}</span>` : ""}</li>`)
    .join("");
  const products = s.iaProducts && s.iaProducts.length ? `<p class="prod"><strong>IA products:</strong> ${esc(s.iaProducts.join(", "))}</p>` : "";
  const soWhat = s.soWhat ? `<p class="sowhat"><strong>So what:</strong> ${esc(s.soWhat)}</p>` : "";
  return `
    <div class="sig">
      <div class="sig-head">
        <span class="glyph">${esc(s.glyph)}</span>
        <span class="sig-label">${esc(s.label)}</span>
        <span class="cat cat-${s.type}">${CATEGORY[s.type] ?? s.type}</span>
      </div>
      <p class="detail">${esc(s.detail)}</p>
      ${soWhat}
      ${products}
      ${evidence ? `<ul class="evidence">${evidence}</ul>` : ""}
    </div>`;
}

function accountBlock(a: AccountInfo | null | undefined): string {
  if (!a) return "";
  const rows: Array<[string, string | null]> = [
    ["Industry", a.industry],
    ["Revenue", a.revenue],
    ["Employees", a.employees],
    ["HQ", a.hq],
    ["Founded", a.founded],
    ["Ownership", a.ownership],
    ["Website", a.website],
  ];
  const cells = rows
    .filter(([, v]) => v)
    .map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(String(v))}</td></tr>`)
    .join("");
  return `
    <section>
      <h2>Account information</h2>
      ${a.description ? `<p class="desc">${esc(a.description)}</p>` : ""}
      ${cells ? `<table class="acct">${cells}</table>` : ""}
    </section>`;
}

export function buildReportHtml(result: ScanResult, account?: AccountInfo | null): string {
  const found = result.signals.filter((s) => s.found);
  const keyFound = found.filter((s) => s.group === "key");
  const supFound = found.filter((s) => s.group === "supporting");
  const undetected = result.signals.filter((s) => !s.found);
  const total = result.signals.length;
  const positive = found.filter((s) => s.type === "positive").length;
  const negative = found.filter((s) => s.type === "negative").length;
  const mixed = found.filter((s) => s.type === "neutral").length;
  const title = `${result.company} — IAsense scan`;

  const section = (heading: string, rows: ScoredSignal[]) =>
    rows.length ? `<section><h2>${esc(heading)} <span class="count">${rows.length}</span></h2>${rows.map(signalBlock).join("")}</section>` : "";

  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #14181f; margin: 32px; line-height: 1.5; }
    h1 { font-size: 24px; margin: 0 0 2px; }
    .sub { color: #5b6472; margin: 0 0 4px; }
    .eyebrow { text-transform: uppercase; letter-spacing: .08em; font-size: 11px; color: #7a8494; font-weight: 600; }
    h2 { font-size: 16px; border-bottom: 1px solid #e5e8ee; padding-bottom: 6px; margin: 26px 0 12px; }
    h2 .count { color: #2563eb; }
    .summary { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 4px; }
    .chip { border: 1px solid #e5e8ee; border-radius: 999px; padding: 4px 12px; font-size: 13px; }
    .chip b { color: #2563eb; }
    .sig { border: 1px solid #e5e8ee; border-radius: 10px; padding: 12px 14px; margin: 10px 0; page-break-inside: avoid; }
    .sig-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
    .glyph { color: #7a8494; }
    .sig-label { font-weight: 600; flex: 1; }
    .cat { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; padding: 2px 8px; border-radius: 999px; }
    .cat-positive { background: #eaf0ff; color: #1d4ed8; }
    .cat-negative { background: #fff1e8; color: #d1531b; }
    .cat-neutral { background: #eef1f5; color: #5b6472; }
    .detail { margin: 4px 0; }
    .sowhat, .prod { margin: 4px 0; font-size: 14px; color: #2a2f39; }
    .evidence { margin: 6px 0 0; padding-left: 18px; font-size: 13px; }
    .evidence a { color: #2563eb; }
    .date { color: #7a8494; }
    table.acct { border-collapse: collapse; margin-top: 8px; }
    table.acct th { text-align: left; color: #7a8494; font-weight: 600; padding: 3px 16px 3px 0; vertical-align: top; white-space: nowrap; }
    .desc { margin: 6px 0; }
    .undetected { color: #5b6472; font-size: 13px; }
    footer { margin-top: 28px; color: #9aa3b2; font-size: 11px; border-top: 1px solid #e5e8ee; padding-top: 8px; }
    @media print { body { margin: 12mm; } a { color: #2563eb; } }
  </style></head><body>
    <div class="eyebrow">Impact Analytics · Account Intelligence</div>
    <h1>${esc(result.company)}</h1>
    <p class="sub">${esc(result.domain)}</p>
    <div class="summary">
      <span class="chip"><b>${found.length}</b> / ${total} signals found</span>
      <span class="chip">${keyFound.length} key</span>
      <span class="chip">${supFound.length} supporting</span>
      <span class="chip">${positive} positive</span>
      <span class="chip">${negative} negative</span>
      <span class="chip">${mixed} mixed</span>
    </div>
    ${accountBlock(account)}
    ${section("Key signals", keyFound)}
    ${section("Supporting signals", supFound)}
    ${undetected.length ? `<section><h2>No detected signals <span class="count">${undetected.length}</span></h2><p class="undetected">${undetected.map((s) => esc(s.label)).join(" · ")}</p></section>` : ""}
    <footer>Generated by IAsense · Account Intelligence${result.cached ? " · cached result" : ""}</footer>
  </body></html>`;
}

/** Render the report into a hidden iframe and open the print dialog (Save as PDF). */
export function downloadScanPdf(result: ScanResult, account?: AccountInfo | null): void {
  const html = buildReportHtml(result, account);
  const iframe = document.createElement("iframe");
  iframe.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(iframe);
  const doc = iframe.contentWindow?.document;
  if (!doc) { document.body.removeChild(iframe); return; }
  doc.open();
  doc.write(html);
  doc.close();
  const done = () => setTimeout(() => iframe.parentNode && document.body.removeChild(iframe), 1500);
  // Give the iframe a moment to lay out before printing.
  setTimeout(() => {
    iframe.contentWindow?.focus();
    iframe.contentWindow?.print();
    done();
  }, 350);
}
