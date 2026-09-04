# Deploying the venue RFP tool

Two independent halves: get Resend able to send as you (Part 1), then get the
app onto Render with the key (Part 2). The tool is useful before either is done
— *Copy* and *Open in mail app* work with no configuration at all — so you can
start outreach today and switch on one-click sending later.

---

## Part 1 — Resend

### 1. Create the account
Sign up at [resend.com](https://resend.com). The free plan covers this project
comfortably: **3,000 emails/month, 100/day, one verified domain, 30-day log
retention**. The full shortlist is 18 venues × 2 nights = 36 emails.

### 2. Add a *sending subdomain*, not the root domain
**Domains → Add Domain →** enter `send.impactanalytics.co`.

> ⚠️ Use the `send.` subdomain. Resend asks for an **MX record** for bounce
> handling, and putting that on the root `impactanalytics.co` would collide with
> the MX records that deliver your actual company email. On a subdomain it is
> isolated and cannot affect the main mailbox.

Pick the region closest to your recipients (US East for New York venues).

### 3. Add the DNS records
Resend shows three records on the **Records** tab. Copy them **verbatim** into
your DNS host (whoever runs `impactanalytics.co` — Cloudflare, GoDaddy, Route 53,
or your IT team):

| Type | Name | Purpose |
|---|---|---|
| `MX` | `send` | Bounce and complaint handling |
| `TXT` | `send` | SPF — authorises Resend to send |
| `TXT` | `resend._domainkey` | DKIM — cryptographic signature |

Do not retype these by hand; the DKIM value is a long public key and one wrong
character fails verification silently.

### 4. Verify
Click **Verify DNS Records**. Most domains go green within 15 minutes;
propagation can take up to 24 hours. SPF/DKIM warnings during that window are
normal and clear themselves.

### 5. Create a scoped API key
**API Keys → Create API Key**

- Name: `ia-venue-rfp`
- Permission: **Sending access** (not Full access — this app only sends)
- Domain: restrict it to `send.impactanalytics.co`

Copy the `re_...` value immediately — Resend shows it exactly once. Treat it as
a password: it goes in Render's environment, never in git.

### 6. Tell IT, briefly
If `impactanalytics.co` publishes a DMARC policy, mention that a new sending
subdomain is live. SPF and DKIM both align to the organisational domain under
relaxed alignment, so a `p=reject` policy on the root will not bounce these —
but it is a courtesy that avoids a surprised security ticket.

### Sending before DNS verifies
Resend lets a brand-new account send from the shared address
`onboarding@resend.dev`, but **only to the email address you signed up with**.
That is enough to prove the plumbing works end to end. Set
`RESEND_FROM=onboarding@resend.dev`, send yourself one RFP, then switch to the
real address once the domain is green. Never point it at a venue while on that
address — it will not be delivered.

---

## Part 2 — Render

### 1. Get the code onto the branch Render watches
The work is on `claude/event-venues-rfp-tool-3dup61`. Render deploys whichever
branch the service is configured to track, usually `main`:

```bash
git checkout main
git merge claude/event-venues-rfp-tool-3dup61
git push origin main
```

Or open a PR from the branch and merge it in GitHub — same result.

### 2. Add the environment variables
`render.yaml` already declares everything except the secret.

**If the service already exists:** Render ignores `sync: false` variables when
updating an existing Blueprint, so add the key by hand —
**Dashboard → your service → Environment → Add Environment Variable**:

| Key | Value |
|---|---|
| `RESEND_API_KEY` | the `re_...` key from Part 1, step 5 |

The rest (`RESEND_FROM`, `RFP_REPLY_TO`, `RFP_SENDER_NAME`, `RFP_SENDER_ORG`)
come from `render.yaml` automatically. Override any of them in the dashboard if
you want different wording without a code change.

**If you are creating the service fresh:** **New → Blueprint**, point it at this
repo, and Render will prompt for `RESEND_API_KEY` during setup.

### 3. Deploy
Saving an environment variable triggers a deploy on its own. Otherwise:
**Manual Deploy → Deploy latest commit**. The Docker build takes a few minutes.

### 4. Verify
Open `https://<your-service>.onrender.com/venues`. The badge top-right should
read **“● Resend connected”** in green rather than the amber warning. Then:

1. Click **Send RFP** on any venue.
2. Replace the To address with your own.
3. **Send via Resend.**

Check it arrives, check the Reply-To is `marketing@impactanalytics.co`, and check
the card flipped to *RFP sent*. Confirm the send appears in Resend's **Emails**
log. Only then start sending to venues.

---

## Two limits of the free plan

**The service sleeps.** A free web service spins down after 15 minutes without
traffic and takes about a minute to wake. The first page load after a quiet
period is slow; nothing is lost.

**The tracker is not durable.** Free instances cannot mount a persistent disk,
so the SQLite file lives on ephemeral container storage and resets on every
deploy and every spin-down. Two ways to handle it:

- *Free:* click **Export tracker** whenever you have made meaningful updates.
  It downloads the whole thing — statuses, notes, send log — as JSON.
- *~$7/month:* upgrade to a Starter instance, then uncomment the `disk:` block
  and the `VENUE_DB_PATH` variable in `render.yaml` and redeploy. State then
  survives everything.

For a six-week booking cycle the free plan plus periodic exports is honestly
fine. Resend's own log is a second record of everything actually sent.

---

## If something goes wrong

| Symptom | Cause |
|---|---|
| Badge still amber after deploy | `RESEND_API_KEY` not saved, or the deploy predates it — redeploy |
| `Resend returned 403` | Key is domain-scoped and `RESEND_FROM` is on a different domain |
| `Resend returned 422` | The `from` domain is not verified yet, or the address is malformed |
| Email sends but never arrives | Still on `onboarding@resend.dev`, which only delivers to your own account address |
| Statuses reset overnight | Expected on free — see the durability note above |
