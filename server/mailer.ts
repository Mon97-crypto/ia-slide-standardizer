/**
 * mailer.ts — send HTML email via Resend (https://resend.com). Enables the admin
 * "top accounts" digest to arrive as a beautifully formatted HTML email instead
 * of a plain-text Gmail draft.
 *
 * Env (server-only secrets):
 *   RESEND_API_KEY   Resend API key (re_...)
 *   RESEND_FROM      From address, e.g. "IAsense <intelligence@impactanalytics.co>"
 *                    (defaults to Resend's test sender until a domain is verified)
 */

export function mailerConfigured(): boolean {
  return !!process.env.RESEND_API_KEY;
}

const FROM = () => process.env.RESEND_FROM || "IAsense <onboarding@resend.dev>";

/** `to` may be a single address or a comma-separated list (for CXO roll-ups). */
export async function sendEmail(to: string, subject: string, html: string): Promise<{ ok: boolean; error?: string }> {
  const key = process.env.RESEND_API_KEY;
  if (!key) return { ok: false, error: "email_not_configured" };
  const recipients = to.split(",").map((s) => s.trim()).filter(Boolean);
  if (!recipients.length || !recipients.every((r) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(r))) {
    return { ok: false, error: "invalid recipient" };
  }
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20_000);
    let res: Response;
    try {
      res = await fetch("https://api.resend.com/emails", {
        method: "POST",
        signal: controller.signal,
        headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
        body: JSON.stringify({ from: FROM(), to: recipients, subject, html }),
      });
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return { ok: false, error: `Resend ${res.status}: ${body.slice(0, 220)}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
}
