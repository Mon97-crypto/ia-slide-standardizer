/**
 * admin.ts — admin-only helpers.
 *   - fetchOwners(): per-person breakdown of Tier 1 "top accounts".
 *   - fetchPersonDigest(): last-7-days developments across a person's top accounts.
 *   - cross-week dedup: items already sent to a person (kept in localStorage) are
 *     filtered out so next week's digest only carries what's new.
 *   - digest builders: a visually appealing HTML preview + a Gmail compose URL.
 * We don't send email server-side — "Send" opens a prefilled Gmail draft.
 */

export interface AdminIntel {
  total: number; found: number; keyFound: number; supFound: number;
  top: Array<{ label: string; detail: string; type: string; soWhat: string }>;
  ageMs: number | null;
}
export interface AdminAccount {
  name: string; domain: string; type: string; status: string; revenue: string;
  owner: string; bdOwner: string; intel: AdminIntel | null;
}
export interface AdminPerson { name: string; email: string; accounts: AdminAccount[]; }
export interface OwnersResponse { ok: boolean; configured: boolean; people: AdminPerson[]; count?: number; error?: string; }

export interface DigestItem {
  account: string; domain: string; headline: string; detail: string; soWhat: string; url: string; date: string;
}
export interface DigestResponse { ok: boolean; items: DigestItem[]; error?: string; }

export async function fetchOwners(): Promise<OwnersResponse> {
  try {
    const res = await fetch("/api/public/admin/owners");
    if (res.status === 403) return { ok: false, configured: true, people: [], error: "forbidden" };
    return (await res.json()) as OwnersResponse;
  } catch (e) {
    return { ok: false, configured: true, people: [], error: (e as Error).message };
  }
}

export async function fetchPersonDigest(person: AdminPerson): Promise<DigestResponse> {
  try {
    const res = await fetch("/api/public/admin/person-digest", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: person.name, accounts: person.accounts.map((a) => ({ name: a.name, domain: a.domain })) }),
    });
    if (res.status === 403) return { ok: false, items: [], error: "forbidden" };
    return (await res.json()) as DigestResponse;
  } catch (e) {
    return { ok: false, items: [], error: (e as Error).message };
  }
}

// ── cross-week dedup (localStorage) ─────────────────────────────────────────
const LOG_KEY = (email: string) => `ia-digest-log:v1:${email.toLowerCase()}`;
function itemKey(it: DigestItem): string {
  const acct = (it.domain || it.account).toLowerCase().replace(/[^a-z0-9]/g, "");
  const head = it.headline.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 48);
  return `${acct}|${head}`;
}
function loadLog(email: string): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(LOG_KEY(email)) || "{}") as Record<string, string>; } catch { return {}; }
}
/** Split a fresh pull into items not seen before vs. those already sent earlier. */
export function dedupItems(email: string, items: DigestItem[]): { fresh: DigestItem[]; skipped: number } {
  const log = loadLog(email);
  const fresh: DigestItem[] = [];
  const seenThisPull = new Set<string>();
  let skipped = 0;
  for (const it of items) {
    const k = itemKey(it);
    if (seenThisPull.has(k)) continue; // de-dupe within the pull too
    seenThisPull.add(k);
    if (log[k]) { skipped++; continue; }
    fresh.push(it);
  }
  return { fresh, skipped };
}
/** Record items as sent so next week's digest excludes them. */
export function markSent(email: string, items: DigestItem[]): void {
  try {
    const log = loadLog(email);
    const stamp = new Date().toISOString().slice(0, 10);
    for (const it of items) log[itemKey(it)] = stamp;
    localStorage.setItem(LOG_KEY(email), JSON.stringify(log));
  } catch { /* best-effort */ }
}

// ── formatting ──────────────────────────────────────────────────────────────
const today = () => { try { return new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" }); } catch { return ""; } };
const weekWindow = () => {
  try {
    const end = new Date();
    const start = new Date(Date.now() - 7 * 864e5);
    const f = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    return `${f(start)} – ${f(end)}`;
  } catch { return "last 7 days"; }
};
const firstName = (name: string) => (name.trim().split(/\s+/)[0] || name);

function groupByAccount(items: DigestItem[]): Array<{ account: string; domain: string; items: DigestItem[] }> {
  const map = new Map<string, { account: string; domain: string; items: DigestItem[] }>();
  for (const it of items) {
    const key = (it.domain || it.account).toLowerCase();
    let g = map.get(key);
    if (!g) { g = { account: it.account, domain: it.domain, items: [] }; map.set(key, g); }
    g.items.push(it);
  }
  return [...map.values()];
}

/** Plain-text digest for the Gmail compose body. */
export function buildDigestText(person: AdminPerson, items: DigestItem[]): string {
  const L: string[] = [];
  L.push(`Hi ${firstName(person.name)},`);
  L.push("");
  L.push(`Here's what moved across your top accounts this week (${weekWindow()}).`);
  L.push("");
  for (const g of groupByAccount(items)) {
    L.push(`━━ ${g.account}${g.domain ? ` (${g.domain})` : ""} ━━`);
    for (const it of g.items) {
      L.push(`• ${it.headline}${it.date ? ` (${it.date})` : ""}`);
      if (it.detail) L.push(`  ${it.detail}`);
      if (it.soWhat) L.push(`  What it means: ${it.soWhat}`);
      if (it.url) L.push(`  Source: ${it.url}`);
    }
    L.push("");
  }
  L.push(`Full dashboard: ${window.location.origin}`);
  L.push("— Sent from IAsense · Account Intelligence");
  return L.join("\n");
}

export function gmailComposeUrl(person: AdminPerson, items: DigestItem[]): string {
  const su = `Your top accounts this week — Account Intelligence (${today()})`;
  const body = buildDigestText(person, items);
  return `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(person.email)}&su=${encodeURIComponent(su)}&body=${encodeURIComponent(body)}`;
}

function esc(s: string): string {
  return (s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
}

/** Visually appealing HTML digest (competitive-intel-digest style). */
export function buildDigestHtml(person: AdminPerson, items: DigestItem[]): string {
  const groups = groupByAccount(items);
  const count = items.length;
  const cards = groups.map((g) => `
    <div class="card">
      <div class="acct-head"><span class="acct-name">${esc(g.account)}</span>${g.domain ? `<span class="dom">${esc(g.domain)}</span>` : ""}</div>
      ${g.items.map((it) => `
        <div class="item">
          <div class="hl">${esc(it.headline)}${it.date ? `<span class="date">${esc(it.date)}</span>` : ""}</div>
          ${it.detail ? `<p class="detail">${esc(it.detail)}</p>` : ""}
          ${it.soWhat ? `<div class="means"><b>What it means:</b> ${esc(it.soWhat)}</div>` : ""}
          ${it.url ? `<a class="src" href="${esc(it.url)}">Source</a>` : ""}
        </div>`).join("")}
    </div>`).join("");

  const empty = `<div class="empty">No new developments across ${esc(firstName(person.name))}'s top accounts in the last 7 days. Nothing to send this week.</div>`;

  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(person.name)} — Top Accounts, This Week</title>
  <style>
    :root{--blue:#2f4fd8;--ink:#14181f;--muted:#7a8494;--line:#e6e9f0;--soft:#f1f4fb;}
    *{box-sizing:border-box;}
    body{font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);margin:0;background:#eef1f6;padding:24px;}
    .wrap{max-width:720px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 10px 40px rgba(20,24,31,.08);}
    .head{border-top:5px solid var(--blue);padding:34px 40px 26px;}
    .brand{display:flex;align-items:center;gap:10px;margin-bottom:20px;}
    .mark{width:26px;height:26px;flex:none;}
    .brandname{font-weight:800;letter-spacing:.02em;font-size:15px;}
    .brandname small{display:block;letter-spacing:.28em;font-size:8px;color:var(--muted);font-weight:700;}
    .eyebrow{text-transform:uppercase;letter-spacing:.1em;font-size:12px;color:var(--blue);font-weight:800;}
    h1{font-family:Georgia,"Times New Roman",serif;font-size:32px;line-height:1.12;margin:10px 0 8px;}
    .meta{color:var(--muted);font-size:14px;margin:0;}
    .pill{display:inline-block;margin-top:16px;background:var(--soft);border:1px solid #dfe4f5;color:var(--blue);font-weight:700;font-size:13px;padding:8px 16px;border-radius:999px;}
    .body{padding:22px 40px 40px;}
    .lead{color:#2a2f39;line-height:1.6;margin:6px 0 22px;}
    .card{border:1px solid var(--line);border-radius:14px;padding:8px 18px 14px;margin:16px 0;}
    .acct-head{display:flex;align-items:baseline;gap:10px;border-bottom:1px solid var(--line);padding:12px 0 10px;margin-bottom:6px;}
    .acct-name{font-weight:800;font-size:17px;color:var(--blue);}
    .dom{color:var(--muted);font-size:13px;}
    .item{padding:12px 0;border-bottom:1px dashed var(--line);}
    .item:last-child{border-bottom:none;}
    .hl{font-weight:700;font-size:15px;display:flex;justify-content:space-between;gap:12px;}
    .hl .date{color:var(--muted);font-weight:500;font-size:12px;white-space:nowrap;}
    .detail{margin:5px 0;color:#2a2f39;}
    .means{background:var(--soft);border-radius:9px;padding:9px 12px;margin:8px 0;font-size:14px;}
    .means b{color:var(--blue);}
    .src{font-size:13px;color:var(--blue);text-decoration:none;font-weight:600;}
    .empty{color:var(--muted);text-align:center;padding:30px;border:1px dashed var(--line);border-radius:12px;}
    footer{color:#9aa3b2;font-size:12px;padding:0 40px 30px;}
  </style></head><body><div class="wrap">
    <div class="head">
      <div class="brand">
        <svg class="mark" viewBox="0 0 24 24" aria-hidden><path d="M8.5 2l4 2-2 6-4-2z" fill="#2f4fd8"/><path d="M6 8l3.5 1.5L7 21l-4-2z" fill="#2f4fd8"/><path d="M13 8l6 12H10z" fill="#2f4fd8"/></svg>
        <div class="brandname">IMPACT<small>ANALYTICS</small></div>
      </div>
      <div class="eyebrow">Top Accounts · This Week</div>
      <h1>What moved across your accounts</h1>
      <p class="meta">${esc(person.name)} · ${esc(person.email)} · ${weekWindow()}</p>
      <span class="pill">${count === 0 ? "No new developments this week" : `${count} new development${count === 1 ? "" : "s"} across ${groups.length} account${groups.length === 1 ? "" : "s"}`}</span>
    </div>
    <div class="body">
      <p class="lead">The latest, de-duplicated against what you were sent in prior weeks — only new items from the last 7 days on your Tier 1 accounts, with what each means for outreach.</p>
      ${count === 0 ? empty : cards}
    </div>
    <footer>Generated by IAsense · Account Intelligence · de-duplicated weekly</footer>
  </div></body></html>`;
}

export function previewDigest(person: AdminPerson, items: DigestItem[]): void {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.open();
  w.document.write(buildDigestHtml(person, items));
  w.document.close();
}
