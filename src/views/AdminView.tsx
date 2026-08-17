/**
 * AdminView — admin-only "Team intelligence". Lists every Owner / BD Owner on a
 * Tier 1 account. For each person you "Prepare digest" (fetches last-7-days
 * developments across their top accounts, de-duplicated against prior weeks),
 * then "Preview" the styled digest or "Send via Gmail" (opens a prefilled draft
 * and records the items as sent so next week only shows what's new).
 */
import { useEffect, useState } from "react";
import {
  fetchOwners, fetchPersonDigest, dedupItems, markSent,
  gmailComposeUrl, previewDigest,
  fetchExecRollup, previewExecRollup, execGmailUrl, type ExecRollup,
  type AdminPerson, type DigestItem,
} from "../lib/admin";

type State = "loading" | "ready" | "unconfigured" | "forbidden" | "error";

interface Prep {
  status: "idle" | "loading" | "ready" | "error";
  fresh: DigestItem[];
  skipped: number;
  sent?: boolean;
  sendMsg?: string;
  error?: string;
}
const IDLE: Prep = { status: "idle", fresh: [], skipped: 0 };

export function AdminView() {
  const [people, setPeople] = useState<AdminPerson[]>([]);
  const [state, setState] = useState<State>("loading");
  const [error, setError] = useState("");
  const [prep, setPrep] = useState<Record<number, Prep>>({});
  const [exec, setExec] = useState<{ status: "idle" | "loading" | "done" | "error"; data?: ExecRollup; error?: string }>({ status: "idle" });

  const load = () => {
    setState("loading"); setPrep({});
    fetchOwners().then((r) => {
      if (r.error === "forbidden") { setState("forbidden"); return; }
      if (r.configured === false) { setState("unconfigured"); return; }
      if (!r.ok) { setError(r.error || "Could not load team data."); setState("error"); return; }
      setPeople(r.people); setState("ready");
    });
  };
  useEffect(() => { load(); }, []);

  const prepare = async (i: number, p: AdminPerson) => {
    setPrep((m) => ({ ...m, [i]: { ...IDLE, status: "loading" } }));
    const r = await fetchPersonDigest(p);
    if (!r.ok) { setPrep((m) => ({ ...m, [i]: { ...IDLE, status: "error", error: r.error || "Could not fetch." } })); return; }
    const { fresh, skipped } = dedupItems(p.email, r.items);
    setPrep((m) => ({ ...m, [i]: { status: "ready", fresh, skipped } }));
  };

  // Open a prefilled Gmail draft with the person's digest, and mark items sent.
  const send = (i: number, p: AdminPerson) => {
    const cur = prep[i];
    if (!cur || cur.status !== "ready" || cur.fresh.length === 0) return;
    window.open(gmailComposeUrl(p, cur.fresh), "_blank");
    markSent(p.email, cur.fresh);
    setPrep((m) => ({ ...m, [i]: { ...cur, sent: true, sendMsg: `Gmail draft opened for ${p.email} & marked sent` } }));
  };

  const runExec = async () => {
    setExec({ status: "loading" });
    const d = await fetchExecRollup();
    if (!d.ok) { setExec({ status: "error", error: d.error === "forbidden" ? "Admins only." : d.error || "Could not generate." }); return; }
    setExec({ status: "done", data: d });
  };

  const busy = Object.values(prep).some((p) => p.status === "loading");

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Admin · account intelligence</div>
        <h1 className="h1" style={{ margin: 0 }}>Team <span className="accent">intelligence</span></h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 660 }}>
          Everyone named as an Owner or BD Owner on a Tier 1 account. Prepare each person's weekly digest — the last
          7 days of developments across their top accounts, de-duplicated against what they were already sent — then
          send it as a prefilled Gmail draft.
        </p>
      </div>

      {state === "ready" && people.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
          <span className="secondary" style={{ fontSize: 14 }}>{people.length} {people.length === 1 ? "person" : "people"}</span>
          <div style={{ flex: 1 }} />
          <button onClick={load} disabled={busy} style={btnGhost}>Refresh list</button>
        </div>
      )}

      {state === "ready" && (
        <div className="card" style={{ padding: "10px 14px", marginBottom: 16, background: "var(--ia-blue-soft)", border: "1px solid #dfe4f5", fontSize: 13, color: "var(--ia-blue-dark)", display: "flex", gap: 8 }}>
          <span aria-hidden>ℹ️</span>
          <span>Preparing a digest runs a live 7-day web search (uses Anthropic credits). Items already sent to a person in a prior week are hidden automatically. <strong>Preview</strong> shows the styled digest; <strong>Send email</strong> opens a prefilled Gmail draft (nicely formatted) for you to review and send.</span>
        </div>
      )}

      {state === "ready" && (
        <div className="card" style={{ padding: "16px 18px", marginBottom: 16, borderColor: "var(--ia-blue-soft)", background: "linear-gradient(180deg, var(--ia-blue-soft) 0%, var(--ia-white) 60%)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="eyebrow" style={{ color: "var(--ia-blue-dark)" }}>Executive roll-up · for CXOs</div>
              <div className="secondary" style={{ fontSize: 13, marginTop: 2 }}>One summary of activity across everyone's Tier 1 accounts — the biggest developments this week, ready to forward to leadership.</div>
            </div>
            {exec.status === "idle" && <button onClick={runExec} style={btnPrimary}>Generate roll-up</button>}
            {exec.status === "loading" && (
              <span className="secondary" style={{ fontSize: 13, display: "inline-flex", alignItems: "center", gap: 7 }}>
                <span aria-hidden style={{ width: 7, height: 7, borderRadius: 999, background: "var(--ia-blue)", animation: "pulse 1s ease-in-out infinite" }} />
                Analysing the whole Tier 1 book…
              </span>
            )}
            {(exec.status === "done" || exec.status === "error") && <button onClick={runExec} style={btnGhost}>Regenerate</button>}
          </div>

          {exec.status === "error" && <div style={{ marginTop: 12, color: "var(--ia-orange)", fontSize: 14 }}>{exec.error}</div>}

          {exec.status === "done" && exec.data && (
            <div style={{ marginTop: 14 }}>
              {exec.data.stats && (
                <div className="secondary" style={{ fontSize: 12, marginBottom: 8 }}>{exec.data.stats.accounts} Tier 1 accounts · {exec.data.stats.owners} owners</div>
              )}
              {exec.data.overview && (
                <div style={{ background: "var(--ia-white)", border: "1px solid var(--ia-gray-1)", borderRadius: 12, padding: "12px 14px", fontSize: 14.5, lineHeight: 1.55, marginBottom: 12 }}>{exec.data.overview}</div>
              )}
              {exec.data.highlights.length > 0 ? (
                <ul style={{ margin: "0 0 12px", paddingLeft: 18, lineHeight: 1.6 }}>
                  {exec.data.highlights.slice(0, 5).map((h, i) => (
                    <li key={i} style={{ marginBottom: 4, fontSize: 14 }}>
                      <strong>{h.account}:</strong> {h.headline}
                      {h.date ? <span className="secondary" style={{ fontSize: 12 }}> · {h.date}</span> : null}
                    </li>
                  ))}
                  {exec.data.highlights.length > 5 && <li className="secondary" style={{ fontSize: 13 }}>+ {exec.data.highlights.length - 5} more in the full roll-up</li>}
                </ul>
              ) : (
                <div className="secondary" style={{ fontSize: 14, marginBottom: 12 }}>A quiet week — no material developments across the Tier 1 book.</div>
              )}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button onClick={() => previewExecRollup(exec.data!)} style={btnGhost}>Preview full roll-up</button>
                <button onClick={() => window.open(execGmailUrl(exec.data!), "_blank")} style={btnPrimary}>Open in Gmail (to CXOs)</button>
              </div>
            </div>
          )}
        </div>
      )}

      {state === "loading" && <Centered>Loading team…</Centered>}
      {state === "forbidden" && <Card orange><strong style={{ color: "var(--ia-orange)" }}>Admins only.</strong><p className="secondary" style={{ marginTop: 8, marginBottom: 0 }}>Your account isn't on the admin list.</p></Card>}
      {state === "unconfigured" && <Card><strong>Google Sheet not connected yet.</strong><p className="secondary" style={{ marginTop: 8, marginBottom: 0 }}>Connect the Salesforce sheet to populate the team list.</p></Card>}
      {state === "error" && <Card orange><strong style={{ color: "var(--ia-orange)" }}>Couldn't load.</strong><p className="secondary" style={{ marginTop: 8, marginBottom: 12 }}>{error}</p><button onClick={load} style={btnGhost}>Try again</button></Card>}

      {state === "ready" && (
        people.length === 0 ? (
          <Centered>No Tier 1 accounts with an assigned Owner or BD Owner yet.</Centered>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {people.map((p, i) => {
              const pr = prep[i] ?? IDLE;
              return (
                <div key={i} className="card" style={{ padding: "14px 16px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontWeight: 600 }}>{p.name}</div>
                      <div className="secondary" style={{ fontSize: 13 }}>{p.email} · {p.accounts.length} top account{p.accounts.length === 1 ? "" : "s"}</div>
                    </div>
                    {pr.status === "idle" && <button onClick={() => prepare(i, p)} style={btnPrimary}>Prepare digest</button>}
                    {pr.status === "loading" && (
                      <span className="secondary" style={{ fontSize: 13, display: "inline-flex", alignItems: "center", gap: 7 }}>
                        <span aria-hidden style={{ width: 7, height: 7, borderRadius: 999, background: "var(--ia-blue)", animation: "pulse 1s ease-in-out infinite" }} />
                        Researching last 7 days…
                      </span>
                    )}
                    {pr.status === "error" && <button onClick={() => prepare(i, p)} style={{ ...btnGhost, color: "var(--ia-orange)", borderColor: "var(--ia-orange)" }}>Retry</button>}
                    {pr.status === "ready" && (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <button onClick={() => previewDigest(p, pr.fresh)} style={btnGhost}>Preview</button>
                        <button onClick={() => send(i, p)} disabled={pr.fresh.length === 0} style={pr.fresh.length ? btnPrimary : btnDisabled}>
                          {pr.sent ? "Re-open email" : "Send email"}
                        </button>
                        <button onClick={() => prepare(i, p)} style={btnGhost}>Re-check</button>
                      </div>
                    )}
                  </div>
                  {pr.status === "ready" && (
                    <div style={{ marginTop: 10, fontSize: 13 }}>
                      {pr.fresh.length === 0 ? (
                        <span className="secondary">No new developments in the last 7 days{pr.skipped ? ` (${pr.skipped} already sent earlier, hidden)` : ""}.</span>
                      ) : (
                        <span>
                          <strong style={{ color: "var(--ia-blue)" }}>{pr.fresh.length}</strong> new item{pr.fresh.length === 1 ? "" : "s"} to send
                          {pr.skipped ? <span className="secondary"> · {pr.skipped} repeat{pr.skipped === 1 ? "" : "s"} hidden</span> : null}
                          {pr.sendMsg ? <span style={{ color: pr.sent ? "#1e7e49" : "var(--ia-orange)" }}> · {pr.sendMsg}</span> : null}
                        </span>
                      )}
                    </div>
                  )}
                  {pr.status === "error" && <div style={{ marginTop: 8, fontSize: 13, color: "var(--ia-orange)" }}>{pr.error}</div>}
                </div>
              );
            })}
          </div>
        )
      )}
    </div>
  );
}

const Centered = ({ children }: { children: React.ReactNode }) => (
  <div style={{ textAlign: "center", padding: "48px 0", color: "var(--ia-gray-3)" }}><p className="secondary">{children}</p></div>
);
const Card = ({ children, orange }: { children: React.ReactNode; orange?: boolean }) => (
  <div className="card" style={{ padding: 20, border: orange ? "1px solid var(--ia-orange)" : undefined }}>{children}</div>
);
const btnGhost: React.CSSProperties = { height: 34, padding: "0 14px", borderRadius: 10, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 13 };
const btnPrimary: React.CSSProperties = { height: 34, padding: "0 14px", borderRadius: 10, border: "none", background: "var(--ia-blue)", color: "#fff", fontWeight: 600, fontSize: 13 };
const btnDisabled: React.CSSProperties = { ...btnPrimary, background: "var(--ia-blue-light)" };
