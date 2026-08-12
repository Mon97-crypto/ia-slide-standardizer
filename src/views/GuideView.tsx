/**
 * GuideView — "How to use". A plain-language guide to every tab and feature, so a
 * new Sales/BD user can get value on day one. Buttons jump straight to each tab.
 */
import type { TabKey } from "../components/Header";

export function GuideView({ isAdmin, onGo }: { isAdmin?: boolean; onGo: (t: TabKey) => void }) {
  return (
    <div>
      <div style={{ marginBottom: 22 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>How to use · account intelligence</div>
        <h1 className="h1" style={{ margin: 0 }}>Get the most out of <span className="accent">IAsense</span></h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 660 }}>
          IAsense turns any retailer into a call-ready account brief — buying signals mapped to what Impact Analytics
          sells, verified company facts, decision-makers and competitor intel. Here's how each tab works.
        </p>
      </div>

      <Callout>
        <b>Good to know across the whole app:</b> sign-in is limited to approved Impact Analytics accounts · all
        intelligence is restricted to the <b>last 180 days</b> · scan results are <b>cached for 30 days</b> (re-runs
        are instant and free — hit <i>Refresh</i> to force a fresh scan) · every fact is grounded in a real, dated,
        clickable source.
      </Callout>

      <Section
        n={1}
        title="Scan"
        tagline="Deep-dive one retailer"
        onGo={() => onGo("scan")}
        goLabel="Open Scan"
        steps={[
          "Paste a company website (e.g. gap.com) — a full URL or a bare domain both work; we clean it up. The Company field is optional.",
          "Click Run scan. IAsense pulls SEC filings, tech stack, news, hiring and Reddit, then shows a live progress bar of the 19 signals being checked.",
          "Read the results: the Signals Found ring, Key vs Supporting signals, and each detected signal with its detail, ‘so what’, the IA products it opens, and source links.",
          "Above the signals you get web-verified Account Information and — if the company is in your Salesforce sheet — a Salesforce card (owner, BD owner, type, status).",
          "Use Check competitor footprint for cited evidence they use/evaluate a rival, Decision makers to pull ICP-fit contacts from Apollo, and Download PDF for a word-for-word brief.",
        ]}
        tips={["Competitor footprint and Decision makers run only when you click them (they use credits). Everything else runs automatically."]}
      />

      <Section
        n={2}
        title="My dashboard"
        tagline="Your book of accounts, from Salesforce"
        onGo={() => onGo("dashboard")}
        goLabel="Open My dashboard"
        steps={[
          "‘Welcome <you>’ is drawn from your login. Two tabs: My Top Accounts (your accounts flagged Tier 1) and All Accounts (all of your accounts).",
          "Click Scan on any row to scan it right here — results open as a dropdown with a live progress bar, no need to leave the page.",
          "Use the + button to select up to 10 accounts, then Scan selected to run them together. On My Top Accounts, Scan all runs the whole list.",
          "Filter by name/owner/status, and Refresh to re-pull the sheet. The bell (admins) jumps to the Admin tab.",
        ]}
        tips={["Only your own accounts are ever loaded here — the full company book is never sent to your browser."]}
      />

      <Section
        n={3}
        title="Bulk upload"
        tagline="Rank a list of accounts at once"
        onGo={() => onGo("bulk")}
        goLabel="Open Bulk upload"
        steps={[
          "Paste up to 30 websites (one per line) or upload a CSV (Company, Website).",
          "Click Run analysis. Each row scans with a live progress bar; a ranked table fills in with Key / Supporting / Total signals.",
          "Click the + on any row to expand the full signal detail. Download CSV exports the summary.",
        ]}
        tips={[
          "Maximum 30 per run. Each account uses several live searches, so run big lists in batches and watch your credit spend.",
          "Cached accounts (scanned in the last 30 days) come back instantly.",
        ]}
      />

      <Section
        n={4}
        title="Ask IAsense"
        tagline="Ask anything about an account"
        onGo={() => onGo("ask")}
        goLabel="Open Ask IAsense"
        steps={[
          "Optionally set a Company focus, then type a question (‘Has Target had inventory problems this year?’).",
          "IAsense researches the web live AND reads your connected Salesforce accounts, then answers in a clean, sourced briefing.",
          "Ask internal questions too — ‘Who owns 1-800-Flowers and what's the status?’ — answered from your CRM data.",
        ]}
        tips={["CRM facts are cited as ‘per Impact Analytics CRM’; market facts get web source links."]}
      />

      {isAdmin && (
        <Section
          n={5}
          title="Admin"
          tagline="Team intelligence (admins only)"
          onGo={() => onGo("admin")}
          goLabel="Open Admin"
          steps={[
            "See everyone named as an Owner or BD Owner on a Tier 1 account, with their email.",
            "Click Prepare digest to pull the last 7 days of developments across that person's top accounts — automatically de-duplicated against what they were sent in prior weeks.",
            "Preview opens the styled digest; Send email delivers it as formatted HTML (needs RESEND_API_KEY), or falls back to a Gmail draft.",
          ]}
          tips={["Preparing a digest runs a live 7-day web search per person (uses credits). Only new items carry over week to week."]}
        />
      )}

      <div className="card" style={{ padding: 20, marginTop: 6 }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>A good weekly rhythm</div>
        <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.9, color: "var(--ia-black)" }}>
          <li>Open <b>My dashboard</b> → <b>Scan all</b> your top accounts to refresh their signals.</li>
          <li>Skim the results; run <b>Competitor footprint</b> + <b>Decision makers</b> on the hottest ones.</li>
          <li>Use <b>Ask IAsense</b> for anything specific before a call, and <b>Download PDF</b> for the brief.</li>
          {isAdmin && <li>On <b>Admin</b>, prepare and send each rep their weekly top-accounts digest.</li>}
        </ol>
      </div>
    </div>
  );
}

function Section({
  n, title, tagline, steps, tips, onGo, goLabel,
}: {
  n: number; title: string; tagline: string; steps: string[]; tips?: string[]; onGo: () => void; goLabel: string;
}) {
  return (
    <div className="card" style={{ padding: "18px 20px", marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <span style={{ width: 30, height: 30, borderRadius: 999, background: "var(--ia-blue-soft)", color: "var(--ia-blue-dark)", fontWeight: 700, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{n}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="h2" style={{ fontSize: 19, margin: 0 }}>{title}</div>
          <div className="secondary" style={{ fontSize: 13 }}>{tagline}</div>
        </div>
        <button onClick={onGo} style={{ height: 34, padding: "0 14px", borderRadius: 10, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-blue)", fontWeight: 600, fontSize: 13 }}>{goLabel} →</button>
      </div>
      <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.75 }}>
        {steps.map((s, i) => <li key={i} style={{ marginBottom: 4 }}>{s}</li>)}
      </ol>
      {tips && tips.length > 0 && (
        <div style={{ marginTop: 12, display: "grid", gap: 6 }}>
          {tips.map((t, i) => (
            <div key={i} style={{ display: "flex", gap: 8, fontSize: 13, color: "var(--ia-gray-3)" }}>
              <span aria-hidden>💡</span><span>{t}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Callout({ children }: { children: React.ReactNode }) {
  return (
    <div className="card" style={{ padding: "14px 16px", marginBottom: 18, background: "var(--ia-blue-soft)", border: "1px solid #dfe4f5", fontSize: 14, color: "var(--ia-blue-dark)", lineHeight: 1.6 }}>
      {children}
    </div>
  );
}
