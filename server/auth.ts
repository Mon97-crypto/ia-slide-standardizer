/**
 * auth.ts — Google SSO, restricted to a single email domain (default
 * impactanalytics.co). Enterprise-safe by construction:
 *   - Server-side OAuth 2.0 Authorization Code flow. The client secret NEVER
 *     leaves the server and is read only from env (GOOGLE_CLIENT_SECRET).
 *   - The allowed domain is enforced on Google's VERIFIED email claim, server-side.
 *   - The session is a signed (HMAC-SHA256, SESSION_SECRET) token in an HttpOnly,
 *     Secure, SameSite=Lax cookie. No token or secret is ever exposed to the browser.
 *   - CSRF-protected with a state nonce cookie.
 *
 * Nothing is hardcoded: with GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / SESSION_SECRET
 * unset, auth is disabled (open) so local dev still runs; set all three (on Render)
 * to enforce sign-in. The redirect URI is derived from the request, so it works on
 * any host without a hardcoded URL.
 */

import type { Hono } from "hono";
import { getCookie, setCookie, deleteCookie } from "hono/cookie";
import { createHmac, timingSafeEqual, randomBytes } from "node:crypto";

// Who may sign in. Access is granted if the verified email is in ALLOWED_EMAILS
// (an explicit comma-separated allowlist, any domain) OR ends in ALLOWED_EMAIL_DOMAIN.
// Set ALLOWED_EMAIL_DOMAIN="" to disable the domain rule and use the allowlist only.
const ALLOWED_DOMAIN = (process.env.ALLOWED_EMAIL_DOMAIN ?? "impactanalytics.co").toLowerCase().trim();
const ALLOWED_EMAILS = new Set(
  (process.env.ALLOWED_EMAILS ?? "")
    .toLowerCase()
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
);

function isAllowed(email: string): boolean {
  if (!email) return false;
  if (ALLOWED_EMAILS.has(email)) return true;
  if (ALLOWED_DOMAIN && email.endsWith(`@${ALLOWED_DOMAIN}`)) return true;
  return false;
}

const SESSION_TTL = 60 * 60 * 12; // 12 hours
const SESSION_COOKIE = "ia_session";
const STATE_COOKIE = "ia_oauth_state";

export function authEnabled(): boolean {
  return !!(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET && process.env.SESSION_SECRET);
}

interface SessionPayload {
  email: string;
  name: string;
  exp: number;
}

function b64url(input: string | Buffer): string {
  return Buffer.from(input).toString("base64url");
}
function sign(data: string, secret: string): string {
  return createHmac("sha256", secret).update(data).digest("base64url");
}

function createSession(email: string, name: string, secret: string): string {
  const body: SessionPayload = { email, name, exp: Math.floor(Date.now() / 1000) + SESSION_TTL };
  const data = b64url(JSON.stringify(body));
  return `${data}.${sign(data, secret)}`;
}

function verifySession(token: string | undefined, secret: string): SessionPayload | null {
  if (!token) return null;
  const dot = token.indexOf(".");
  if (dot < 0) return null;
  const data = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expected = sign(data, secret);
  const a = Buffer.from(sig);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const body = JSON.parse(Buffer.from(data, "base64url").toString()) as SessionPayload;
    if (typeof body.exp !== "number" || body.exp < Math.floor(Date.now() / 1000)) return null;
    return body;
  } catch {
    return null;
  }
}

function decodeJwtPayload(jwt: string): Record<string, unknown> {
  const parts = jwt.split(".");
  if (parts.length < 2) return {};
  try {
    return JSON.parse(Buffer.from(parts[1], "base64url").toString()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function baseUrl(c: { req: { header: (n: string) => string | undefined } }): string {
  const proto = c.req.header("x-forwarded-proto") || "https";
  const host = c.req.header("x-forwarded-host") || c.req.header("host") || "";
  return `${proto}://${host}`;
}

/**
 * Registers the auth routes + the middleware that protects /api/public/*.
 * MUST be called BEFORE the /api/public route handlers are defined so the
 * middleware wraps them.
 */
export function registerAuth(app: Hono): void {
  // Gate the scanning API when auth is enabled.
  app.use("/api/public/*", async (c, next) => {
    if (!authEnabled()) return next();
    const sess = verifySession(getCookie(c, SESSION_COOKIE), process.env.SESSION_SECRET as string);
    if (!sess) return c.json({ error: "unauthorized" }, 401);
    return next();
  });

  // Who am I? (used by the client to decide whether to show the login screen)
  app.get("/api/auth/me", (c) => {
    if (!authEnabled()) return c.json({ authenticated: true, authDisabled: true });
    const sess = verifySession(getCookie(c, SESSION_COOKIE), process.env.SESSION_SECRET as string);
    if (!sess) return c.json({ authenticated: false });
    return c.json({ authenticated: true, email: sess.email, name: sess.name });
  });

  // Start the Google OAuth flow.
  app.get("/auth/login", (c) => {
    if (!authEnabled()) return c.redirect("/");
    const state = randomBytes(16).toString("hex");
    setCookie(c, STATE_COOKIE, state, { httpOnly: true, secure: true, sameSite: "Lax", path: "/", maxAge: 600 });
    const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    url.searchParams.set("client_id", process.env.GOOGLE_CLIENT_ID as string);
    url.searchParams.set("redirect_uri", `${baseUrl(c)}/auth/callback`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", "openid email profile");
    url.searchParams.set("state", state);
    // Only hint Google to a specific hosted domain in pure-domain mode. With an
    // explicit allowlist (e.g. personal Gmail), let the user pick any account.
    if (ALLOWED_DOMAIN && ALLOWED_EMAILS.size === 0 && ALLOWED_DOMAIN !== "gmail.com") {
      url.searchParams.set("hd", ALLOWED_DOMAIN);
    }
    url.searchParams.set("prompt", "select_account");
    return c.redirect(url.toString());
  });

  // OAuth callback: exchange code, verify domain, set the session.
  app.get("/auth/callback", async (c) => {
    if (!authEnabled()) return c.redirect("/");
    const code = c.req.query("code");
    const state = c.req.query("state");
    const savedState = getCookie(c, STATE_COOKIE);
    deleteCookie(c, STATE_COOKIE, { path: "/" });
    if (!code || !state || !savedState || state !== savedState) return c.redirect("/?auth=error");

    try {
      const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
        method: "POST",
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          code,
          client_id: process.env.GOOGLE_CLIENT_ID as string,
          client_secret: process.env.GOOGLE_CLIENT_SECRET as string,
          redirect_uri: `${baseUrl(c)}/auth/callback`,
          grant_type: "authorization_code",
        }),
      });
      if (!tokenRes.ok) return c.redirect("/?auth=error");
      const tok = (await tokenRes.json()) as { id_token?: string };
      if (!tok.id_token) return c.redirect("/?auth=error");

      // The id_token came directly from Google's token endpoint over TLS, so its
      // claims are trusted. Enforce a verified email in the allowed domain.
      const claims = decodeJwtPayload(tok.id_token);
      const email = String(claims.email ?? "").toLowerCase();
      const verified = claims.email_verified === true || claims.email_verified === "true";
      const name = String(claims.name ?? email);
      if (!email || !verified || !isAllowed(email)) {
        return c.redirect("/?auth=denied");
      }

      const session = createSession(email, name, process.env.SESSION_SECRET as string);
      setCookie(c, SESSION_COOKIE, session, { httpOnly: true, secure: true, sameSite: "Lax", path: "/", maxAge: SESSION_TTL });
      return c.redirect("/");
    } catch {
      return c.redirect("/?auth=error");
    }
  });

  app.get("/auth/logout", (c) => {
    deleteCookie(c, SESSION_COOKIE, { path: "/" });
    return c.redirect("/");
  });
}
