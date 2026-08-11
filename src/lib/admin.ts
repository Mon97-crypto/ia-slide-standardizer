/**
 * admin.ts — admin-only helpers: fetch the per-person breakdown of Tier 1 "top
 * accounts", and build (a) a Gmail compose URL prefilled with each person's
 * intelligence digest, and (b) a styled HTML preview of that digest.
 *
 * We don't send email server-side (no mail provider / secret). Instead each
 * "Send intelligence" opens Gmail's compose window prefilled with the recipient,
 * subject and a plain-text digest — the admin reviews and hits Send.
 */

export interface AdminIntel {
  total: number;
  found: number;
  keyFound: number;
  supFound: number;
  top: Array<{ label: string; detail: string; type: string; soWhat: string }>;
  ageMs: number | null;
}

export interface AdminAccount {
  name: string;
  domain: string;
  type: string;
  status: string;
  revenue: string;
  owner: string;
  bdOwner: string;
  intel: AdminIntel | null;
}

export interface AdminPerson {
  name: string;
  email: string;
  accounts: AdminAccount[];
}

export interface OwnersResponse {
  ok: boolean;
  configured: boolean;
  people: AdminPerson[];
  count?: number;
  error?: string;
}

export async function fetchOwners(): Promise<OwnersResponse> {
  try {
    const res = await fetch("/api/public/admin/owners");
    if (res.status === 403) return { ok: false, configured: true, people: [], error: "forbidden" };
    return (await res.json()) as OwnersResponse;
  } catch (e) {
    return { ok: false, configured: true, people: [], error: (e as Error).message };
  }
}

const today = () => {
  try {
    return new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return "";
  }
};
const firstName = (name: string) => (name.trim().split(/\s+/)[0] || name);
const fmtRevenue = (raw: string) => {
  if (!raw) return "";
  const n = Number(raw.replace(/[^0-9.]/g, ""));
  if (!raw.match(/^[\s$]*[\d.,]+\s*$/) || !isFinite(n) || n === 0) return raw;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1).replace(/\.0$/, "")}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${n}`;
};

/** Plain-text digest body for the Gmail compose window. */
export function buildDigestText(person: AdminPerson): string {
  const origin = window.location.origin;
  const lines: string[] = [];
  lines.push(`Hi ${firstName(person.name)},`);
  lines.push("");
  lines.push(`Here's the latest intelligence on your Tier 1 top accounts (${person.accounts.length}).`);
  lines.push("");
  for (const a of person.accounts) {
    lines.push(`━━ ${a.name} (${a.domain}) ━━`);
    const meta = [a.type, a.status, fmtRevenue(a.revenue)].filter(Boolean).join(" · ");
    if (meta) lines.push(meta);
    if (a.intel && a.intel.found > 0) {
      lines.push(`Signals found: ${a.intel.found}/${a.intel.total} (${a.intel.keyFound} key, ${a.intel.supFound} supporting)`);
      for (const s of a.intel.top) {
        lines.push(`  • ${s.label}: ${s.detail}`);
      }
      const so = a.intel.top.find((s) => s.soWhat)?.soWhat;
      if (so) lines.push(`  What it means: ${so}`);
    } else {
      lines.push("No recent scan on file — open the account in IAsense to run a fresh scan.");
    }
    lines.push("");
  }
  lines.push(`Full dashboard: ${origin}`);
  lines.push("— Sent from IAsense · Account Intelligence");
  return lines.join("\n");
}

/** Gmail compose URL prefilled for this person. */
export function gmailComposeUrl(person: AdminPerson): string {
  const su = `Your top accounts — Account Intelligence (${today()})`;
  const body = buildDigestText(person);
  return `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(person.email)}&su=${encodeURIComponent(su)}&body=${encodeURIComponent(body)}`;
}

function esc(s: string): string {
  return (s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
}
const CAT: Record<string, string> = { positive: "Positive", negative: "Negative", neutral: "Mixed" };

/** Styled HTML preview of a person's digest (opens in a new tab). */
export function buildDigestHtml(person: AdminPerson): string {
  const cards = person.accounts
    .map((a) => {
      const meta = [a.type, a.status, fmtRevenue(a.revenue)].filter(Boolean).join(" · ");
      const signals = a.intel && a.intel.found > 0
        ? `<p class="sig">Signals found: <b>${a.intel.found}/${a.intel.total}</b> · ${a.intel.keyFound} key · ${a.intel.supFound} supporting</p>
           <ul>${a.intel.top.map((s) => `<li><span class="cat cat-${s.type}">${CAT[s.type] ?? s.type}</span> <strong>${esc(s.label)}</strong> — ${esc(s.detail)}</li>`).join("")}</ul>
           ${a.intel.top.find((s) => s.soWhat) ? `<div class="means"><b>What it means:</b> ${esc(a.intel.top.find((s) => s.soWhat)!.soWhat)}</div>` : ""}`
        : `<p class="none">No recent scan on file — run a fresh scan in IAsense to enrich this account.</p>`;
      return `<div class="card"><div class="eyebrow">${esc(a.owner === person.name ? "OWNED ACCOUNT" : "BD-OWNED ACCOUNT")}</div>
        <h3>${esc(a.name)} <span class="dom">${esc(a.domain)}</span></h3>
        ${meta ? `<p class="meta">${esc(meta)}</p>` : ""}${signals}</div>`;
    })
    .join("");
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(person.name)} — Top Accounts Intelligence</title>
  <style>
    body{font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#14181f;margin:0;background:#f4f6fa;}
    .wrap{max-width:720px;margin:0 auto;background:#fff;}
    .head{border-top:4px solid #2f4fd8;padding:32px 36px 24px;}
    .eyebrow{text-transform:uppercase;letter-spacing:.09em;font-size:12px;color:#2f4fd8;font-weight:700;}
    h1{font-family:Georgia,"Times New Roman",serif;font-size:30px;margin:8px 0 6px;}
    .sub{color:#7a8494;margin:0;}
    .body{padding:8px 36px 40px;}
    .lead{color:#2a2f39;line-height:1.6;margin:18px 0 26px;}
    .card{border:1px solid #e5e8ee;border-radius:12px;padding:16px 18px;margin:14px 0;}
    .card h3{margin:2px 0 6px;font-size:18px;}
    .dom{color:#2f4fd8;font-weight:400;font-size:14px;}
    .meta{color:#5b6472;margin:0 0 8px;font-size:14px;}
    .sig{margin:6px 0;}
    ul{margin:8px 0;padding-left:18px;}
    li{margin:4px 0;}
    .cat{font-size:10px;font-weight:700;text-transform:uppercase;padding:1px 7px;border-radius:999px;}
    .cat-positive{background:#eaf0ff;color:#1d4ed8;} .cat-negative{background:#fff1e8;color:#d1531b;} .cat-neutral{background:#eef1f5;color:#5b6472;}
    .means{background:#f1f4fb;border-radius:8px;padding:10px 12px;margin-top:8px;font-size:14px;}
    .none{color:#7a8494;font-size:14px;}
    footer{color:#9aa3b2;font-size:12px;padding:0 36px 32px;}
  </style></head><body><div class="wrap">
    <div class="head"><div class="eyebrow">Account Intelligence · Top Accounts</div>
      <h1>Your top accounts, ${esc(firstName(person.name))}</h1>
      <p class="sub">${esc(person.email)} · ${today()} · ${person.accounts.length} Tier 1 account${person.accounts.length === 1 ? "" : "s"}</p></div>
    <div class="body"><p class="lead">Here's the latest intelligence on the Tier 1 accounts you own, grouped by account with the signals we've detected and what they mean for outreach.</p>
    ${cards}</div>
    <footer>Generated by IAsense · Account Intelligence</footer>
  </div></body></html>`;
}

export function previewDigest(person: AdminPerson): void {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.open();
  w.document.write(buildDigestHtml(person));
  w.document.close();
}
