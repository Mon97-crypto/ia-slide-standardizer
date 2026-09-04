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

### Step 0 — work out which situation you are in

Open [dashboard.render.com](https://dashboard.render.com) and look for a service
named **ia-slide-standardizer**.

- **Not there** → Path A. You are creating the service for the first time.
- **It is there** → check whether it is Blueprint-managed: open the service and
  look for a **Blueprint** link in its settings, or check the **Blueprints** tab
  in the dashboard.
  - Listed under Blueprints → **Path B**. `render.yaml` drives it.
  - Not listed → **Path C**. It was created by hand, so `render.yaml` is
    *ignored* and every environment variable must be set in the dashboard.

Getting this wrong is the most common cause of "I set the variables and nothing
changed", so spend the thirty seconds.

---

### Path A — first deploy (no service yet)

**1. Put the code on `main`.**

```bash
git checkout main
git merge claude/event-venues-rfp-tool-3dup61
git push origin main
```

**2.** Dashboard → **+ New** → **Blueprint**.

**3.** Connect GitHub if you have not already, then **Connect** next to
`Mon97-crypto/ia-slide-standardizer`. If the repo is not listed, click *Configure
account* and grant Render access to it.

**4.** Render reads `render.yaml` and shows what it will create: one web service,
`ia-slide-standardizer`, Docker runtime, Free plan. Give the Blueprint a name and
confirm the branch is **main**.

**5.** It prompts for **`RESEND_API_KEY`** — this is the `sync: false` variable.
Paste the `re_...` key from Part 1. (You can leave it blank and add it later; the
tool just runs without one-click send until you do.)

**6.** Click **Deploy Blueprint**. The first Docker build takes roughly 3–6
minutes — it installs tesseract via apt and then the Python dependencies.

**7.** Follow the **Logs** tab. You are waiting for gunicorn's
`Booting worker with pid ...` and then **Your service is live**.

**8.** Your URL is `https://ia-slide-standardizer.onrender.com` — or with a random
suffix if that name is taken globally. The exact URL is at the top of the service
page.

**9.** Open `/venues` on it.

---

### Path B — service exists and is Blueprint-managed

**1. Find which branch it deploys.** Service → **Settings** → **Build & Deploy** →
**Branch**. It is almost certainly `main`.

**2. Merge into that branch and push.**

```bash
git checkout main
git merge claude/event-venues-rfp-tool-3dup61
git push origin main
```

**3.** If **Auto-Deploy** is *On* (Settings → Build & Deploy → Auto-Deploy), the
push starts a build by itself — watch the **Events** tab. If it is *Off*, click
**Manual Deploy** → **Deploy latest commit**.

**4. Add the secret by hand.** Render *ignores `sync: false` variables when
updating an existing Blueprint*, so it will not prompt you. Service →
**Environment** → **Add Environment Variable** → `RESEND_API_KEY` = your `re_...`
key → **Save Changes**. Saving triggers another deploy on its own.

The other four variables (`RESEND_FROM`, `RFP_REPLY_TO`, `RFP_SENDER_NAME`,
`RFP_SENDER_ORG`) sync from `render.yaml` automatically on this path.

**5.** Wait for **Your service is live**, then open `/venues`.

---

### Path C — service exists but was created manually

`render.yaml` does nothing for this service. Same merge and deploy as Path B,
but in step 4 add **all five** variables in the Environment tab:

| Key | Value |
|---|---|
| `RESEND_API_KEY` | your `re_...` key |
| `RESEND_FROM` | `Impact Analytics Events <events@send.impactanalytics.co>` |
| `RFP_REPLY_TO` | `marketing@impactanalytics.co` |
| `RFP_SENDER_NAME` | `Impact Analytics — Events Team` |
| `RFP_SENDER_ORG` | `Impact Analytics` |

(Only the first is strictly required — the rest have sensible defaults in code.
Set them anyway so the sender identity is explicit rather than implied.)

---

### Deploying without touching `main` first

If you would rather see it running before merging, point the existing service at
the feature branch: Settings → Build & Deploy → **Branch** →
`claude/event-venues-rfp-tool-3dup61` → Save. It deploys from there. Remember to
point it back at `main` afterwards.

---

### Verify the deploy

1. Open `https://<your-service>.onrender.com/` — the slide standardiser should
   still work exactly as before. The venue tool is additive; it changes nothing
   about the existing app.
2. Open `/venues`. You should see 18 venue cards.
3. Check the badge top-right: **“● Resend connected”** in green means the key is
   live. Amber means it is missing or the deploy predates it.
4. Click **Send RFP** on any venue, change the To address to your own, and
   **Send via Resend**. Confirm it arrives, that Reply-To is
   `marketing@impactanalytics.co`, that the card flipped to *RFP sent*, and that
   the send shows in Resend's **Emails** log.

Only after that test should you send to an actual venue.

---

### If the build fails

| Symptom | Likely cause |
|---|---|
| Build fails at `apt-get` or `pip install` | Transient network — click **Manual Deploy → Deploy latest commit** and try again |
| `ModuleNotFoundError: venue_rfp` | The merge did not land on the deployed branch — check the Events tab shows the right commit |
| Deploy succeeds, `/venues` returns 404 | Deployed commit predates the tool; redeploy latest |
| Health check failing | `healthCheckPath` is `/`, which is the slide standardiser — unrelated to the venue tool |

A fresh clone of this branch on Python 3.11 (the Dockerfile's base image)
installs from `requirements.txt` and boots under gunicorn with both routes
serving 200, so a build failure here is an infrastructure hiccup rather than a
code problem.

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
