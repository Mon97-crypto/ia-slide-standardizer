"""RFP body generation and Resend delivery.

Resend is called over plain urllib so the tool adds no new dependency. When
RESEND_API_KEY is unset the UI still composes and copies the RFP — it just
cannot send it.
"""
import json
import os
import urllib.error
import urllib.request

RESEND_ENDPOINT = 'https://api.resend.com/emails'


def config():
    return {
        'api_key': os.environ.get('RESEND_API_KEY', ''),
        'from_address': os.environ.get('RESEND_FROM', 'Impact Analytics Events <events@impactanalytics.co>'),
        'reply_to': os.environ.get('RFP_REPLY_TO', 'marketing@impactanalytics.co'),
        'sender_name': os.environ.get('RFP_SENDER_NAME', 'Impact Analytics — Events Team'),
        'sender_org': os.environ.get('RFP_SENDER_ORG', 'Impact Analytics'),
        'sender_phone': os.environ.get('RFP_SENDER_PHONE', ''),
    }


def is_configured():
    return bool(config()['api_key'])


def build_subject(venue, night):
    return (
        f"Private event enquiry — {night['date']} · "
        f"{night['headcount']} · {config()['sender_org']}"
    )


_ASKS_COMMON = [
    "Availability on the date above, and the largest hold you can place while we confirm",
    "Food & beverage minimum and/or room fee — and whether NRF week carries a premium",
    "Beverage packages, including a substantial non-alcoholic selection",
    "Deposit schedule, payment terms and the cancellation policy",
    "Dietary accommodation — we expect vegetarian, vegan, halal and gluten-free guests",
    "Whether service charge, administrative fee and tax are included in the quoted figures",
]

_ASKS_SEATED = [
    "Confirmation that the room is fully private, with no other diners seated in it",
    "Menu formats you would recommend at this headcount — set menu, family style or tasting",
    "AV: screen or projector, and a microphone for a short five-minute welcome",
    "Room layout options — one long table versus rounds — and your recommendation for conversation",
]

_ASKS_RECEPTION = [
    "Confirmation the space holds this many guests standing, comfortably rather than at capacity",
    "Passed canapé and station options, and how many pieces per guest you would advise",
    "Bar setup — number of bar positions and staffing for a group this size",
    "Coat check, and whether guests can arrive across a window rather than all at once",
    "Background music or a sound system we could plug into, and whether a short welcome is workable",
]


def build_body(venue, night, event):
    cfg = config()
    space = venue.get('space') or 'your private dining space'
    is_reception = 'reception' in night['format'].lower() or night['id'] == 'saturday'
    asks = _ASKS_COMMON[:1] + (_ASKS_RECEPTION if is_reception else _ASKS_SEATED) + _ASKS_COMMON[1:]

    lines = [
        f"Hello {venue['name']} events team,",
        "",
        f"I'm writing from {cfg['sender_org']} about a private event during "
        f"{event['name']} week in January ({event['conference_dates']}, Javits Center).",
        "",
        f"  Event      {night['format']}",
        f"  Date       {night['date']}",
        f"  Guests     {night['headcount']}",
        f"  Timing     approximately {night['window']}",
        f"  Space      {space}",
        "",
        f"The group is {night['audience']}.",
        "",
        "Could you please come back to me on the following:",
        "",
    ]
    lines += [f"  {i}. {ask}" for i, ask in enumerate(asks, start=1)]
    lines += [
        "",
        "We are comparing a short list of venues over the next two weeks and will "
        "move quickly once we have proposals in hand. A PDF pack or a call both work — "
        "whichever is easier for you.",
        "",
        "Thank you,",
        cfg['sender_name'],
        cfg['sender_org'],
    ]
    if cfg['sender_phone']:
        lines.append(cfg['sender_phone'])
    lines.append(cfg['reply_to'])
    return "\n".join(lines)


def send(to_email, subject, body, reply_to=None):
    """Send via Resend. Returns (ok, message_id, error)."""
    cfg = config()
    if not cfg['api_key']:
        return False, '', 'RESEND_API_KEY is not set on this deployment.'
    payload = {
        'from': cfg['from_address'],
        'to': [to_email],
        'subject': subject,
        'text': body,
    }
    reply = reply_to or cfg['reply_to']
    if reply:
        payload['reply_to'] = reply

    req = urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f"Bearer {cfg['api_key']}",
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8') or '{}')
        return True, data.get('id', ''), ''
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', 'replace')[:400]
        return False, '', f'Resend returned {exc.code}: {detail}'
    except Exception as exc:  # network, timeout, bad JSON
        return False, '', f'{type(exc).__name__}: {exc}'
