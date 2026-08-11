/**
 * AdminView — admin-only "Team intelligence". Lists every person named as an
 * Owner or BD Owner on a Tier 1 account, with their email and top-account count.
 * "Send intelligence" opens Gmail's compose window prefilled with a digest of
 * THAT person's top accounts; "Preview" opens the styled digest in a new tab.
 */
import { useEffect, useState } from "react";
import { fetchOwners, gmailComposeUrl, previewDigest, type AdminPerson } from "../lib/admin";

type State = "loading" | "ready" | "unconfigured" | "forbidden" | "error";

export function AdminView() {
  const [people, setPeople] = useState<AdminPerson[]>([]);
  const [state, setState] = useState<State>("loading");
  const [error, setError] = useState("");

  const load = () => {
    setState("loading");
    fetchOwners().then((r) => {
      if (r.error === "forbidden") { setState("forbidden"); return; }
      if (r.configured === false) { setState("unconfigured"); return; }
      if (!r.ok) { setError(r.error || "Could not load team data."); setState("error"); return; }
      setPeople(r.people);
      setState("ready");
    });
  };
  useEffect(() => { load(); }, []);

  const sendOne = (p: AdminPerson) => window.open(gmailComposeUrl(p), "_blank");
  // "Send to all" opens one Gmail compose per person. Browsers throttle multiple
  // window.open calls, so we stagger them slightly; if popups are blocked, the
  // admin can still send each from its own row button.
  const sendAll = () => {
    people.forEach((p, i) => setTimeout(() => window.open(gmailComposeUrl(p), "_blank"), i * 600));
  };

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Admin · account intelligence</div>
        <h1 className="h1" style={{ margin: 0 }}>Team <span className="accent">intelligence</span></h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 640 }}>
          Everyone named as an Owner or BD Owner on a Tier 1 account. Send each person a digest of their own top
          accounts — it opens a prefilled Gmail draft so you can review before sending.
        </p>
      </div>

      {state === "ready" && people.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <span className="secondary" style={{ fontSize: 14 }}>{people.length} {people.length === 1 ? "person" : "people"}</span>
          <div style={{ flex: 1 }} />
          <button onClick={load} style={btnGhost}>Refresh</button>
          <button onClick={sendAll} style={btnPrimary}>Send intelligence to all</button>
        </div>
      )}

      {state === "loading" && (
        <div style={{ textAlign: "center", padding: "56px 0", color: "var(--ia-gray-3)" }}>
          <p className="secondary">Loading team…</p>
        </div>
      )}

      {state === "forbidden" && (
        <div className="card" style={{ padding: 20, border: "1px solid var(--ia-orange)" }}>
          <strong style={{ color: "var(--ia-orange)" }}>Admins only.</strong>
          <p className="secondary" style={{ marginTop: 8, marginBottom: 0 }}>Your account isn't on the admin list.</p>
        </div>
      )}

      {state === "unconfigured" && (
        <div className="card" style={{ padding: 20 }}>
          <strong>Google Sheet not connected yet.</strong>
          <p className="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
            Connect the Salesforce sheet (see the dashboard) to populate the team list.
          </p>
        </div>
      )}

      {state === "error" && (
        <div className="card" style={{ padding: 20, border: "1px solid var(--ia-orange)" }}>
          <strong style={{ color: "var(--ia-orange)" }}>Couldn't load.</strong>
          <p className="secondary" style={{ marginTop: 8, marginBottom: 12 }}>{error}</p>
          <button onClick={load} style={btnGhost}>Try again</button>
        </div>
      )}

      {state === "ready" && (
        people.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 0", color: "var(--ia-gray-3)" }}>
            <p className="secondary">No Tier 1 accounts with an assigned Owner or BD Owner yet.</p>
          </div>
        ) : (
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14, minWidth: 720 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--ia-gray-1)" }}>
                  <Th>Person</Th>
                  <Th>Email</Th>
                  <Th right>Top accounts</Th>
                  <Th right>Scanned</Th>
                  <Th right> </Th>
                </tr>
              </thead>
              <tbody>
                {people.map((p, i) => {
                  const scanned = p.accounts.filter((a) => a.intel && a.intel.found > 0).length;
                  return (
                    <tr key={i} style={{ borderTop: "1px solid var(--ia-gray-1)" }} className="hover-lift">
                      <td style={td}><span style={{ fontWeight: 600 }}>{p.name}</span></td>
                      <td style={td}><span className="secondary">{p.email}</span></td>
                      <td style={{ ...td, textAlign: "right" }} className="tnum">{p.accounts.length}</td>
                      <td style={{ ...td, textAlign: "right" }} className="tnum secondary">{scanned}/{p.accounts.length}</td>
                      <td style={{ ...td, textAlign: "right", whiteSpace: "nowrap" }}>
                        <button onClick={() => previewDigest(p)} style={{ ...btnGhost, marginRight: 8 }}>Preview</button>
                        <button onClick={() => sendOne(p)} style={btnPrimary}>Send intelligence</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}

const Th = ({ children, right }: { children: React.ReactNode; right?: boolean }) => (
  <th className="eyebrow" style={{ textAlign: right ? "right" : "left", padding: "12px 16px", fontWeight: 600, whiteSpace: "nowrap" }}>{children}</th>
);
const td: React.CSSProperties = { padding: "12px 16px", verticalAlign: "middle" };
const btnGhost: React.CSSProperties = { height: 34, padding: "0 14px", borderRadius: 10, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 13 };
const btnPrimary: React.CSSProperties = { height: 34, padding: "0 14px", borderRadius: 10, border: "none", background: "var(--ia-blue)", color: "#fff", fontWeight: 600, fontSize: 13 };
