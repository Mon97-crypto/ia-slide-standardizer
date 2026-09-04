# NRF 2027 venue RFP tool

Shortlisted New York venues for the two NRF 2027 evenings, with one-click RFP
sending through Resend and outreach tracking. Mounted on the existing Flask app
at **`/venues`**.

## The two briefs

| Night | Date | Format | Headcount |
|---|---|---|---|
| Saturday reception | Sat 9 Jan 2027 | Standing cocktail reception, passed food | up to 50 |
| Sunday exec dinner | Sun 10 Jan 2027 | Seated, private or fully partitioned room | 30–35 |

NRF Retail's Big Show 2027 runs 10–12 January at the Javits Center, so venues
are ranked by walking distance from Javits (`proximity_rank` in the data file).

See **[DEPLOY.md](DEPLOY.md)** for the Resend and Render setup runbook.

## Configuration

All optional — without them the tool still drafts, copies and hands off RFPs to
your mail client; only the in-app send needs a key.

| Variable | Default | Purpose |
|---|---|---|
| `RESEND_API_KEY` | _unset_ | Enables the "Send via Resend" button |
| `RESEND_FROM` | `Impact Analytics Events <events@impactanalytics.co>` | Must be a domain verified in Resend |
| `RFP_REPLY_TO` | `marketing@impactanalytics.co` | Reply-to and the address in the signature |
| `RFP_SENDER_NAME` | `Impact Analytics — Events Team` | Signature name |
| `RFP_SENDER_ORG` | `Impact Analytics` | Used in subject and body |
| `RFP_SENDER_PHONE` | _unset_ | Added to the signature when set |
| `VENUE_DB_PATH` | `venue_rfp/data/outreach.db` | SQLite tracker location |

**Persistence:** on Render's free plan the container disk is ephemeral, so point
`VENUE_DB_PATH` at a mounted disk (or export the tracker with the *Export
tracker* button) if the history needs to survive a redeploy.

## Editing the shortlist

`data/venues.json` holds the event brief and the venue records. `email_confidence`
is one of:

- `verified` — the address is published by the venue or its hospitality group
- `form_only` — the venue publishes no address; use their enquiry form, or paste
  an address into the card once you have one
- `unconfirmed` — an address exists but is a general line, not the events desk

Cover images and email addresses edited in the UI are stored in SQLite and
override the JSON, so the data file stays the clean source of record.

## Routes

| Route | Purpose |
|---|---|
| `GET /venues/` | The board |
| `GET /venues/api/venues` | Catalog merged with tracker state |
| `GET /venues/api/draft/<venue>/<night>` | Prefilled to/subject/body |
| `POST /venues/api/send` | Send via Resend, log it, mark as sent |
| `POST /venues/api/outreach/<venue>/<night>` | Status and notes |
| `POST /venues/api/meta/<venue>` | Cover image / email override |
| `GET /venues/api/history` | Send log |
| `GET /venues/api/export` | Download the whole tracker as JSON |
