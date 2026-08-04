/**
 * LoginScreen — the opening screen. Sign in with Google; access is restricted to
 * @impactanalytics.co accounts (enforced server-side). Shows a clear message when
 * access is denied or an auth error occurred.
 */
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden style={{ flexShrink: 0 }}>
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.71-1.57 2.68-3.89 2.68-6.62z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
      <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.47.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
    </svg>
  );
}

export function LoginScreen() {
  const params = new URLSearchParams(window.location.search);
  const denied = params.get("auth") === "denied";
  const error = params.get("auth") === "error";
  const deniedEmail = params.get("e") || "";
  const allowedDomain = params.get("d") || "";

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div className="card anim-fade-up" style={{ width: "100%", maxWidth: 420, padding: 36, textAlign: "center" }}>
        <img src="/ia_logo.png" alt="Impact Analytics" style={{ height: 36, width: "auto", margin: "0 auto 22px", display: "block" }} />
        <div className="eyebrow" style={{ marginBottom: 8 }}>Sales and BD · account intelligence</div>
        <h1 className="h2" style={{ fontSize: 26, margin: "0 0 8px" }}>Sign in to continue</h1>
        <p className="secondary" style={{ margin: "0 auto 24px", maxWidth: 320 }}>
          This tool is for authorized Impact Analytics users. Sign in with your approved Google account to continue.
        </p>

        {denied && (
          <div style={{ marginBottom: 16, padding: "10px 14px", borderRadius: 13, border: "1px solid var(--ia-orange)", background: "#fff1e8", fontSize: 14, textAlign: "left" }}>
            <strong style={{ color: "var(--ia-orange)" }}>Access denied.</strong>{" "}
            {deniedEmail ? <>You signed in as <strong>{deniedEmail}</strong>. </> : "That Google account is not authorized. "}
            {allowedDomain
              ? <>Access is limited to <strong>@{allowedDomain}</strong> accounts — sign in with that account.</>
              : <>The server has no allowed domain or email list configured. Set <code>ALLOWED_EMAIL_DOMAIN</code> or <code>ALLOWED_EMAILS</code>.</>}
          </div>
        )}
        {error && (
          <div style={{ marginBottom: 16, padding: "10px 14px", borderRadius: 13, border: "1px solid var(--ia-gray-2)", background: "var(--ia-white)", fontSize: 14, textAlign: "left" }}>
            Sign-in could not be completed. Please try again.
          </div>
        )}

        <a
          href="/auth/login"
          style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 10, width: "100%", height: 46, borderRadius: 13, border: "1px solid var(--ia-gray-1)", background: "var(--ia-white)", color: "var(--ia-black)", fontWeight: 600, fontSize: 15, textDecoration: "none" }}
        >
          <GoogleMark />
          Sign in with Google
        </a>

        <p className="secondary" style={{ margin: "20px 0 0", fontSize: 12 }}>
          Secured with Google SSO. Your session is encrypted and expires automatically.
        </p>
      </div>
    </div>
  );
}
