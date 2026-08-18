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

export interface RollupHighlight {
  account: string; domain: string; headline: string; detail: string; whyItMatters: string; url: string; date: string;
}
export interface ExecRollup {
  ok: boolean; overview: string; highlights: RollupHighlight[];
  stats?: { accounts: number; owners: number }; generatedAt?: number; error?: string;
}

export async function fetchExecRollup(): Promise<ExecRollup> {
  try {
    const res = await fetch("/api/public/admin/exec-rollup", { method: "POST" });
    if (res.status === 403) return { ok: false, overview: "", highlights: [], error: "forbidden" };
    return (await res.json()) as ExecRollup;
  } catch (e) {
    return { ok: false, overview: "", highlights: [], error: (e as Error).message };
  }
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

// ── shared digest log (server-side, shared by all admins) ───────────────────
// Dedup, send-history and last-digest all live on the server so BOTH admins see
// one truth (a send by one admin is reflected for the other). See server/digest-log.ts.
export type SendChannel = "email" | "gmail";
export interface SendRecord { at: string; count: number; channel?: SendChannel; }

/** De-dupe a fresh pull against what any admin has already sent this person, and
 * return the last stored digest (so it can be re-sent even after dedup). */
export async function dedupItems(email: string, items: DigestItem[]): Promise<{ fresh: DigestItem[]; skipped: number; last: DigestItem[] }> {
  try {
    const res = await fetch("/api/public/admin/digest-dedup", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, items }),
    });
    const d = (await res.json()) as { ok?: boolean; fresh?: DigestItem[]; skipped?: number; last?: DigestItem[] };
    if (!d.ok) return { fresh: items, skipped: 0, last: [] };
    return { fresh: d.fresh ?? [], skipped: d.skipped ?? 0, last: d.last ?? [] };
  } catch {
    return { fresh: items, skipped: 0, last: [] };
  }
}

/** Record a send (marks items sent + appends to the shared audit trail). */
export async function recordSend(email: string, items: DigestItem[], channel: SendChannel): Promise<SendRecord | null> {
  try {
    const res = await fetch("/api/public/admin/digest-record", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, items, channel }),
    });
    const d = (await res.json()) as { ok?: boolean; record?: SendRecord };
    return d.ok ? (d.record ?? null) : null;
  } catch { return null; }
}

/** Last-sent record for many people at once (for the admin list). */
export async function fetchLastSends(emails: string[]): Promise<Record<string, SendRecord | null>> {
  try {
    const res = await fetch("/api/public/admin/digest-log", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ emails }),
    });
    const d = (await res.json()) as { ok?: boolean; last?: Record<string, SendRecord | null> };
    return d.ok ? (d.last ?? {}) : {};
  } catch { return {}; }
}

/** Full send history for one person (newest first) — for an audit view. */
export async function fetchHistory(email: string): Promise<SendRecord[]> {
  try {
    const res = await fetch("/api/public/admin/digest-log", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const d = (await res.json()) as { ok?: boolean; history?: SendRecord[] };
    return d.ok ? (d.history ?? []) : [];
  } catch { return []; }
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

/** Beautified plain-text digest for the Gmail compose body (Gmail carries text
 * only, so we structure it with clear per-account sections and spacing). */
export function buildDigestText(person: AdminPerson, items: DigestItem[]): string {
  const groups = groupByAccount(items);
  const RULE = "──────────────────────────────────────────";
  const L: string[] = [];

  L.push("IMPACT ANALYTICS · ACCOUNT INTELLIGENCE");
  L.push("Top accounts · this week");
  L.push(RULE);
  L.push("");
  L.push(`Hi ${firstName(person.name)},`);
  L.push("");
  L.push(`Here's what moved across your top accounts this week (${weekWindow()}).`);
  L.push(`${items.length} new development${items.length === 1 ? "" : "s"} across ${groups.length} account${groups.length === 1 ? "" : "s"}, de-duplicated against prior weeks.`);
  L.push("");

  groups.forEach((g, gi) => {
    L.push(RULE);
    L.push(`▌ ${g.account.toUpperCase()}${g.domain ? `   ·   ${g.domain}` : ""}`);
    L.push(RULE);
    g.items.forEach((it, i) => {
      L.push("");
      L.push(`${i + 1}. ${it.headline}${it.date ? `   (${it.date})` : ""}`);
      if (it.detail) L.push(`   ${it.detail}`);
      if (it.soWhat) L.push(`   ➜ What it means: ${it.soWhat}`);
      if (it.url) L.push(`   🔗 ${it.url}`);
    });
    L.push("");
    if (gi < groups.length - 1) L.push("");
  });

  L.push(RULE);
  L.push(`Open the dashboard:  ${window.location.origin}`);
  L.push("Sent from IAsense · Account Intelligence · de-duplicated weekly");
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

// Email-safe HTML: inline styles + literal colors only (email clients strip CSS
// variables and most <style> rules), table wrapper for width — renders the same
// in Gmail as in the preview.
const C = { blue: "#2f4fd8", bluedark: "#1d4ed8", ink: "#14181f", muted: "#7a8494", line: "#e6e9f0", soft: "#eef2fd", body: "#2a2f39" };
const FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";

function itemHtml(it: DigestItem): string {
  return `<div style="padding:13px 0;border-bottom:1px dashed ${C.line};">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>
      <td style="font:700 15px/1.3 ${FONT};color:${C.ink};padding-right:10px;">${esc(it.headline)}</td>
      <td align="right" style="font:500 12px ${FONT};color:${C.muted};white-space:nowrap;vertical-align:top;">${esc(it.date)}</td>
    </tr></table>
    ${it.detail ? `<p style="margin:6px 0;font:400 14px/1.55 ${FONT};color:${C.body};">${esc(it.detail)}</p>` : ""}
    ${it.soWhat ? `<div style="background:${C.soft};border-radius:9px;padding:10px 12px;margin:8px 0;font:400 14px/1.5 ${FONT};color:${C.ink};"><b style="color:${C.blue};">What it means:</b> ${esc(it.soWhat)}</div>` : ""}
    ${it.url ? `<a href="${esc(it.url)}" style="font:600 13px ${FONT};color:${C.blue};text-decoration:none;">Source →</a>` : ""}
  </div>`;
}

function cardHtml(g: { account: string; domain: string; items: DigestItem[] }): string {
  const items = g.items.map(itemHtml).join("");
  const n = g.items.length;
  const initial = (g.account.trim()[0] || "•").toUpperCase();
  const badge = `${n} update${n === 1 ? "" : "s"}`;
  return `<div style="border:1px solid ${C.line};border-radius:14px;padding:4px 18px 14px;margin:16px 0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border-bottom:1px solid ${C.line};">
      <tr>
        <td width="38" style="padding:13px 0 11px;vertical-align:middle;">
          <div style="width:34px;height:34px;border-radius:8px;background:${C.soft};color:${C.blue};font:800 15px ${FONT};text-align:center;line-height:34px;">${esc(initial)}</div>
        </td>
        <td style="padding:13px 0 11px 12px;vertical-align:middle;">
          <div style="font:800 17px ${FONT};color:${C.blue};">${esc(g.account)}</div>${g.domain ? `<div style="font:400 12px ${FONT};color:${C.muted};margin-top:1px;">${esc(g.domain)}</div>` : ""}
        </td>
        <td align="right" style="padding:13px 0 11px;vertical-align:middle;white-space:nowrap;">
          <span style="display:inline-block;background:${C.soft};border:1px solid #dfe4f5;color:${C.blue};font:700 11px ${FONT};padding:5px 11px;border-radius:999px;">${badge}</span>
        </td>
      </tr>
    </table>${items}</div>`;
}

/** Visually appealing, email-safe HTML digest (competitive-intel-digest style). */
export function buildDigestHtml(person: AdminPerson, items: DigestItem[]): string {
  const groups = groupByAccount(items);
  const count = items.length;
  const pill = count === 0 ? "No new developments this week" : `${count} new development${count === 1 ? "" : "s"} across ${groups.length} account${groups.length === 1 ? "" : "s"}`;
  const cards = count === 0
    ? `<div style="color:${C.muted};text-align:center;padding:30px;border:1px dashed ${C.line};border-radius:12px;font:400 14px ${FONT};">No new developments across ${esc(firstName(person.name))}'s top accounts in the last 7 days. Nothing to send this week.</div>`
    : groups.map(cardHtml).join("");

  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(person.name)} — Top Accounts, This Week</title></head>
<body style="margin:0;padding:0;background:#eef1f6;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f6;border-collapse:collapse;"><tr><td align="center" style="padding:24px 12px;">
    <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:640px;max-width:640px;background:#ffffff;border-radius:16px;border-collapse:separate;overflow:hidden;">
      <tr><td style="border-top:5px solid ${C.blue};padding:32px 36px 24px;">
        <img src="${window.location.origin}/ia_logo.png" alt="Impact Analytics" width="176" height="58" style="display:block;border:0;width:176px;height:58px;" />
        <div style="margin-top:22px;font:800 12px ${FONT};letter-spacing:.1em;text-transform:uppercase;color:${C.blue};">Top Accounts · This Week</div>
        <h1 style="font:400 32px/1.12 Georgia,'Times New Roman',serif;color:${C.ink};margin:10px 0 8px;">What moved across your accounts</h1>
        <p style="font:400 14px ${FONT};color:${C.muted};margin:0;">${esc(person.name)} · ${esc(person.email)} · ${weekWindow()}</p>
        <div style="display:inline-block;margin-top:16px;background:${C.soft};border:1px solid #dfe4f5;color:${C.blue};font:700 13px ${FONT};padding:8px 16px;border-radius:999px;">${pill}</div>
      </td></tr>
      <tr><td style="padding:18px 36px 38px;">
        <p style="font:400 15px/1.6 ${FONT};color:${C.body};margin:6px 0 20px;">Hi ${esc(firstName(person.name))}, here's what moved on <b style="color:${C.ink};">your accounts</b> this week.</p>
        ${cards}
      </td></tr>
    </table>
  </td></tr></table>
</body></html>`;
}

export function digestSubject(): string {
  return `Your top accounts this week — Account Intelligence (${today()})`;
}

export function previewDigest(person: AdminPerson, items: DigestItem[]): void {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.open();
  w.document.write(buildDigestHtml(person, items));
  w.document.close();
}

// ── Executive roll-up (for CXOs) ────────────────────────────────────────────
export function execSubject(): string {
  return `Executive roll-up — Tier 1 accounts (${today()})`;
}

/** Styled HTML executive roll-up. */
export function buildExecHtml(data: ExecRollup): string {
  const hi = data.highlights || [];
  const stat = data.stats ? `${data.stats.accounts} Tier 1 accounts · ${data.stats.owners} owners` : "";
  const cards = hi.length === 0
    ? `<div style="color:${C.muted};text-align:center;padding:26px;border:1px dashed ${C.line};border-radius:12px;font:400 14px ${FONT};">A quiet week — no material developments across the Tier 1 book in the last 7 days.</div>`
    : hi.map((h, i) => `
      <div style="border:1px solid ${C.line};border-radius:14px;padding:14px 18px;margin:14px 0;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>
          <td style="font:800 12px ${FONT};letter-spacing:.04em;color:${C.blue};text-transform:uppercase;">${i + 1}. ${esc(h.account)}${h.domain ? ` · ${esc(h.domain)}` : ""}</td>
          <td align="right" style="font:500 12px ${FONT};color:${C.muted};white-space:nowrap;">${esc(h.date)}</td>
        </tr></table>
        <div style="font:700 16px/1.35 ${FONT};color:${C.ink};margin:6px 0 4px;">${esc(h.headline)}</div>
        ${h.detail ? `<p style="font:400 14px/1.55 ${FONT};color:${C.body};margin:0 0 6px;">${esc(h.detail)}</p>` : ""}
        ${h.whyItMatters ? `<div style="background:${C.soft};border-radius:9px;padding:9px 12px;font:400 14px/1.5 ${FONT};color:${C.ink};"><b style="color:${C.blue};">Why it matters:</b> ${esc(h.whyItMatters)}</div>` : ""}
        ${h.url ? `<a href="${esc(h.url)}" style="font:600 13px ${FONT};color:${C.blue};text-decoration:none;display:inline-block;margin-top:8px;">Source →</a>` : ""}
      </div>`).join("");

  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Executive roll-up — Tier 1 accounts</title></head>
<body style="margin:0;padding:0;background:#eef1f6;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f6;border-collapse:collapse;"><tr><td align="center" style="padding:24px 12px;">
    <table role="presentation" width="660" cellpadding="0" cellspacing="0" style="width:660px;max-width:660px;background:#ffffff;border-radius:16px;border-collapse:separate;overflow:hidden;">
      <tr><td style="border-top:5px solid ${C.blue};padding:32px 38px 24px;">
        <img src="${window.location.origin}/ia_logo.png" alt="Impact Analytics" width="176" height="58" style="display:block;border:0;width:176px;height:58px;" />
        <div style="margin-top:22px;font:800 12px ${FONT};letter-spacing:.1em;text-transform:uppercase;color:${C.blue};">Executive Roll-up · This Week</div>
        <h1 style="font:400 30px/1.14 Georgia,'Times New Roman',serif;color:${C.ink};margin:10px 0 8px;">Tier 1 account activity</h1>
        <p style="font:400 14px ${FONT};color:${C.muted};margin:0;">${weekWindow()}${stat ? ` · ${stat}` : ""}</p>
      </td></tr>
      <tr><td style="padding:16px 38px 38px;">
        <div style="font:800 12px ${FONT};letter-spacing:.08em;text-transform:uppercase;color:${C.muted};margin:6px 0 4px;">Top developments</div>
        ${cards}
        <p style="font:400 12px ${FONT};color:#9aa3b2;margin:26px 0 0;border-top:1px solid ${C.line};padding-top:14px;">Generated by IAsense · Account Intelligence · across the full Tier 1 book, last 7 days</p>
      </td></tr>
    </table>
  </td></tr></table>
</body></html>`;
}

export function buildExecText(data: ExecRollup): string {
  const RULE = "──────────────────────────────────────────";
  const L: string[] = [];
  L.push("IMPACT ANALYTICS · EXECUTIVE ROLL-UP");
  L.push(`Tier 1 account activity · ${weekWindow()}`);
  if (data.stats) L.push(`${data.stats.accounts} Tier 1 accounts · ${data.stats.owners} owners`);
  L.push(RULE);
  L.push("");
  L.push("TOP DEVELOPMENTS");
  (data.highlights || []).forEach((h, i) => {
    L.push("");
    L.push(`${i + 1}. ${h.account}${h.domain ? ` (${h.domain})` : ""}${h.date ? `   ·   ${h.date}` : ""}`);
    L.push(`   ${h.headline}`);
    if (h.detail) L.push(`   ${h.detail}`);
    if (h.whyItMatters) L.push(`   ➜ Why it matters: ${h.whyItMatters}`);
    if (h.url) L.push(`   🔗 ${h.url}`);
  });
  if (!(data.highlights || []).length) L.push("(A quiet week — no material developments across the Tier 1 book.)");
  L.push("");
  L.push(RULE);
  L.push("Generated by IAsense · Account Intelligence");
  return L.join("\n");
}

/** Gmail compose for the CXOs — recipient left blank for the admin to fill. */
export function execGmailUrl(data: ExecRollup): string {
  return `https://mail.google.com/mail/?view=cm&fs=1&to=&su=${encodeURIComponent(execSubject())}&body=${encodeURIComponent(buildExecText(data))}`;
}

/** Send the styled exec roll-up as HTML email to one or more CXO recipients. */
export async function sendExecEmail(recipients: string, data: ExecRollup): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch("/api/public/admin/send-email", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ to: recipients, subject: execSubject(), html: buildExecHtml(data) }),
    });
    return (await res.json()) as { ok: boolean; error?: string };
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
}

export function previewExecRollup(data: ExecRollup): void {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.open();
  w.document.write(buildExecHtml(data));
  w.document.close();
}

/** Send the rendered HTML digest via the server mailer. Returns an error code so
 * the UI can fall back to Gmail-compose when email isn't configured. */
export async function sendDigestEmail(person: AdminPerson, items: DigestItem[]): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch("/api/public/admin/send-email", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ to: person.email, subject: digestSubject(), html: buildDigestHtml(person, items) }),
    });
    return (await res.json()) as { ok: boolean; error?: string };
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
}
