"""Turn a web page into a PDF of what is visible on it.

Someone reads a competitor's launch post, a pricing page or an analyst write-up
and wants it filed rather than bookmarked, because the page will change. This
fetches the page on the server, keeps the parts a reader actually sees -
headings, prose, lists, tables and images, in the order they appear - and lays
them out as a branded PDF.

It is deliberately not a browser screenshot. The deployment runs in a small
container, and a headless Chromium needs more memory than it has, so there is
no rendering engine here: the result reproduces the page's content, not its
visual design. Anything that only exists as behaviour - links, menus, hover
states, video, scripted widgets, paywalled or signed-in content - cannot
survive that and does not appear. The PDF says so on its first page.

The URL comes from a user and is fetched by the server, so this is an SSRF
surface. Unlike the document fetcher there is no host allowlist to hide behind,
so every hop of every redirect is resolved and refused if it lands on an
address that is not globally routable.
"""
from __future__ import annotations

import io
import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, Image as RLImage,
                                KeepTogether, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from . import pdf_fonts
from .config import Config

BLUE = colors.HexColor("#264CD7")
BLACK = colors.HexColor("#1C1B1B")
GREY = colors.HexColor("#6C6A66")
LINE = colors.HexColor("#E4E4E4")
OFF_WHITE = colors.HexColor("#F4F4F6")
FIELD = colors.Color(38 / 255, 75 / 255, 215 / 255)

MAX_REDIRECTS = 5
MAX_HTML_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_IMAGES = 14
MIN_IMAGE_PIXELS = 120          # below this it is an icon, a spacer or a pixel
FETCH_TIMEOUT = 20
IMAGE_TIMEOUT = 8
TOTAL_BUDGET = 55               # seconds, so the request never outlives the proxy
USER_AGENT = ("Mozilla/5.0 (compatible; IA-CompetitorIntelligence/1.0; "
              "+page-to-pdf)")


class CaptureError(Exception):
    """Raised when a page cannot be captured, with a message worth showing."""


@dataclass
class Capture:
    url: str
    final_url: str
    title: str
    blocks: list = field(default_factory=list)
    truncated: bool = False


# ─── the network side ──────────────────────────────────────────────────────

def normalise(url: str) -> str:
    """Accept what a person pastes and return something fetchable."""
    url = (url or "").strip()
    if not url:
        raise CaptureError("Paste a link first.")
    if len(url) > 2000:
        raise CaptureError("That link is too long to be real.")
    # A scheme has to be recognised before anything is prepended. Testing for
    # "://" alone misses javascript: and data:, which have no slashes, and
    # those would then be rewritten into https://javascript:alert(1) and
    # accepted as an ordinary address rather than refused.
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):(.*)$", url, re.S)
    if match is None:
        url = "https://" + url                # people paste bare domains
    elif match.group(1).lower() not in ("http", "https"):
        if re.match(r"^\d+(?:[/?#]|$)", match.group(2)):
            url = "https://" + url            # host:port, not a scheme
        else:
            raise CaptureError("Only http and https links can be captured.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise CaptureError("Only http and https links can be captured.")
    if not parsed.hostname:
        raise CaptureError("That does not look like a web address.")
    if parsed.username or parsed.password:
        # Credentials in a URL are how an SSRF probe reaches an internal
        # service, and nothing legitimate here needs them.
        raise CaptureError("Remove the credentials from that link.")
    return urlunparse(parsed)


def assert_public(hostname: str) -> None:
    """Refuse a host that resolves anywhere but the public internet.

    Every address the name resolves to is checked, not just the first, so a
    name answering with one public and one private address is still refused.
    A name could in principle answer differently between this lookup and the
    connection that follows; closing that would mean pinning the socket to a
    verified address, which is more machinery than an internal tool with
    authenticated users needs.
    """
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise CaptureError(f"Could not find {hostname}.") from exc
    if not infos:
        raise CaptureError(f"Could not find {hostname}.")
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise CaptureError(
                "That address is on a private network, so it will not be "
                "fetched.")


def _get(url: str, deadline: float, accept: str, max_bytes: int):
    """Fetch one resource, checking every redirect hop for itself."""
    import requests

    with requests.Session() as session:
        return _walk_redirects(session, url, deadline, accept, max_bytes)


def _walk_redirects(session, url: str, deadline: float, accept: str,
                    max_bytes: int):
    for _ in range(MAX_REDIRECTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            raise CaptureError("That page took too long to fetch.")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise CaptureError("That link redirected somewhere unsupported.")
        assert_public(parsed.hostname or "")
        try:
            response = session.get(
                url, timeout=min(FETCH_TIMEOUT, remaining),
                allow_redirects=False, stream=True,
                headers={"User-Agent": USER_AGENT, "Accept": accept,
                         "Accept-Language": "en-GB,en;q=0.9"})
        except Exception as exc:
            raise CaptureError(f"Could not reach that page: {exc}") from exc

        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise CaptureError("That page redirected to nowhere.")
            url = urljoin(url, location)
            continue

        if response.status_code in (401, 403):
            raise CaptureError(
                "That page refused the request. Pages behind a sign-in or a "
                "bot check cannot be captured.")
        if response.status_code == 404:
            raise CaptureError("That page was not found (404).")
        if response.status_code >= 400:
            raise CaptureError(
                f"That site returned status {response.status_code}.")

        chunks, total = [], 0
        for block in response.iter_content(65536):
            total += len(block)
            if total > max_bytes:
                response.close()
                raise CaptureError("That page is larger than the capture limit.")
            chunks.append(block)
        response.close()
        return b"".join(chunks), response.url or url, \
            (response.headers.get("content-type") or "").lower()

    raise CaptureError("That link redirected too many times.")


def _decode(data: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type)
    if match:
        try:
            return data.decode(match.group(1), "replace")
        except LookupError:
            pass
    head = data[:4096]
    match = re.search(rb'charset=["\']?([\w-]+)', head, re.I)
    if match:
        try:
            return data.decode(match.group(1).decode("ascii"), "replace")
        except (LookupError, UnicodeDecodeError):
            pass
    return data.decode("utf-8", "replace")


# ─── reading the page ──────────────────────────────────────────────────────

# Removed outright: none of it is page content a reader would say they saw.
_DROP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe",
              "canvas", "video", "audio", "object", "embed", "form", "input",
              "select", "textarea", "button", "nav", "dialog", "picture-source"}

# Removed by class or id, inside the main region as well as outside it. Kept
# narrow on purpose: a broad pattern like "header" or "nav" also matches real
# article furniture and starts eating the content.
_CHROME = re.compile(
    r"cookie|consent|gdpr|newsletter|subscribe|signup|sign-up|paywall|"
    r"social-share|sharing|share-buttons|advert|\bads?\b|sponsored|promo|"
    r"popup|modal|lightbox|breadcrumb|skip-to|screen-reader|visually-hidden|"
    r"related-post|related-article|recirc|comment|disqus|back-to-top",
    re.I)

# Where the page is likely to keep the thing it is about. A semantic container
# is a strong enough signal to trust on a short page; the class-name guesses
# are not, so they have to clear the same bar as the density fallback.
_STRONG_HINTS = ["article", "main", "[role=main]"]
_WEAK_HINTS = [".post-content", ".entry-content", ".article-body",
               ".article-content", "#content", ".content"]

# Dropped unless they sit inside the article, where a <header> usually holds
# the headline and byline and a <footer> the author note. At page level they
# are the site's masthead, navigation and small print.
_EDGE_TAGS = ["header", "footer", "aside"]

_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}
_SKIP_TEXT = re.compile(
    r"^(accept( all)?( cookies)?|reject( all)?|manage (cookies|preferences)|"
    r"subscribe|sign ?up|log ?in|sign ?in|share|tweet|menu|search|skip to "
    r"(main )?content)$", re.I)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _is_chrome(tag) -> bool:
    """Page furniture rather than page content."""
    attrs = getattr(tag, "attrs", None)
    if not attrs:                        # already removed, or not a real tag
        return False
    classes = attrs.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    marker = " ".join(classes) + " " + str(attrs.get("id") or "")
    if marker.strip() and _CHROME.search(marker):
        return True
    return attrs.get("aria-hidden") == "true" or "hidden" in attrs


def _page_title(soup, url: str) -> str:
    for getter in (
        lambda: (soup.find("meta", property="og:title") or {}).get("content"),
        lambda: soup.title.get_text() if soup.title else None,
        lambda: soup.h1.get_text() if soup.h1 else None,
    ):
        try:
            title = _clean_text(getter() or "")
        except Exception:
            title = ""
        if title:
            return title[:180]
    return urlparse(url).hostname or "Captured page"


def _pick_region(soup):
    """Find the part of the page the page is actually about.

    Sites disagree on markup, so semantic containers are tried first and a
    density score settles it otherwise: the container holding the most
    paragraph text wins. Falling back to the whole body would drag in the
    navigation and the footer of every site that uses neither.
    """
    for selectors, floor in ((_STRONG_HINTS, 120), (_WEAK_HINTS, 400)):
        for selector in selectors:
            try:
                found = soup.select(selector)
            except Exception:
                continue
            best = max((node for node in found if not _is_chrome(node)),
                       key=lambda node: len(node.get_text(" ", strip=True)),
                       default=None)
            if best is not None and len(best.get_text(" ", strip=True)) > floor:
                return best

    best, best_score = None, 0
    for node in soup.find_all(["div", "section", "td"]):
        score = sum(len(p.get_text(" ", strip=True))
                    for p in node.find_all("p", recursive=False))
        score += sum(len(p.get_text(" ", strip=True)) * 0.6
                     for p in node.find_all("p", recursive=True)
                     if p.parent is not node)
        if score > best_score:
            best, best_score = node, score
    return best if best_score > 400 else (soup.body or soup)


def _list_items(node) -> list:
    items = []
    for item in node.find_all("li", recursive=False):
        text = _clean_text(item.get_text(" ", strip=True))
        if text and not _SKIP_TEXT.match(text):
            items.append(text[:600])
    return items[:60]


def _table_rows(node) -> list:
    rows = []
    for row in node.find_all("tr")[:40]:
        cells = [_clean_text(cell.get_text(" ", strip=True))[:200]
                 for cell in row.find_all(["th", "td"])[:8]]
        if any(cells):
            rows.append(cells)
    if len(rows) < 2:
        return []
    width = max(len(row) for row in rows)
    return [row + [""] * (width - len(row)) for row in rows]


def _image_source(tag, base_url: str) -> str:
    """Resolve the source a browser would actually load.

    Lazy loading means src is often a placeholder and the real file sits in
    data-src or srcset, so a naive read of src collects grey spacers.
    """
    for attribute in ("data-src", "data-original", "data-lazy-src", "src"):
        value = (tag.get(attribute) or "").strip()
        if value and not value.startswith("data:image/gif"):
            return urljoin(base_url, value)
    srcset = (tag.get("srcset") or tag.get("data-srcset") or "").strip()
    if srcset:
        candidate = srcset.split(",")[-1].strip().split(" ")[0]
        if candidate:
            return urljoin(base_url, candidate)
    return ""


def extract(html: str, base_url: str) -> tuple[str, list]:
    """Read a page into an ordered list of blocks."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    title = _page_title(soup, base_url)

    for tag in soup.find_all(list(_DROP_TAGS)):
        tag.decompose()
    # Snapshot first and re-check as we go: decomposing a container destroys
    # its descendants, and a destroyed tag still sitting in the list has no
    # attributes left to read.
    for tag in list(soup.find_all(True)):
        if not getattr(tag, "decomposed", False) and _is_chrome(tag):
            tag.decompose()
    for tag in list(soup.find_all(_EDGE_TAGS)):
        if (not getattr(tag, "decomposed", False)
                and tag.find_parent(["article", "main"]) is None):
            tag.decompose()

    region = _pick_region(soup)
    blocks: list = []
    seen_text: set = set()

    def emit(block):
        if block["kind"] in ("heading", "para", "quote"):
            key = block["text"][:160].lower()
            if key in seen_text:
                return                       # sites repeat a headline verbatim
            seen_text.add(key)
        blocks.append(block)

    def walk(node, depth=0):
        if depth > 24 or len(blocks) > 900:
            return
        for child in getattr(node, "children", []):
            name = getattr(child, "name", None)
            if name is None:
                continue
            if name in _HEADINGS:
                text = _clean_text(child.get_text(" ", strip=True))
                if text and not _SKIP_TEXT.match(text):
                    emit({"kind": "heading", "level": _HEADINGS[name],
                          "text": text[:300]})
            elif name == "p":
                text = _clean_text(child.get_text(" ", strip=True))
                image = child.find("img")
                if image is not None:
                    source = _image_source(image, base_url)
                    if source:
                        emit({"kind": "image", "src": source,
                              "alt": _clean_text(image.get("alt") or "")})
                if len(text) > 1 and not _SKIP_TEXT.match(text):
                    emit({"kind": "para", "text": text[:4000]})
            elif name in ("ul", "ol"):
                items = _list_items(child)
                if items:
                    emit({"kind": "list", "ordered": name == "ol",
                          "items": items})
            elif name == "table":
                rows = _table_rows(child)
                if rows:
                    emit({"kind": "table", "rows": rows})
                else:
                    walk(child, depth + 1)
            elif name == "blockquote":
                text = _clean_text(child.get_text(" ", strip=True))
                if text:
                    emit({"kind": "quote", "text": text[:1200]})
            elif name == "pre":
                text = child.get_text("\n", strip=False)[:2000]
                if text.strip():
                    emit({"kind": "code", "text": text})
            elif name == "img":
                source = _image_source(child, base_url)
                if source:
                    emit({"kind": "image", "src": source,
                          "alt": _clean_text(child.get("alt") or "")})
            elif name == "figure":
                image = child.find("img")
                caption = child.find("figcaption")
                if image is not None:
                    source = _image_source(image, base_url)
                    if source:
                        emit({"kind": "image", "src": source,
                              "alt": _clean_text(
                                  (caption.get_text(" ", strip=True)
                                   if caption else "") or image.get("alt") or "")})
            elif name == "hr":
                emit({"kind": "rule"})
            elif name in ("br", "link", "meta"):
                continue
            else:
                walk(child, depth + 1)

    walk(region)

    # Some sites lay paragraphs out as bare divs, which the walk sees as
    # containers and descends past. If almost nothing came back, fall back to
    # the region's text split on blank lines rather than returning an empty PDF.
    if sum(1 for b in blocks if b["kind"] == "para") < 2:
        text = region.get_text("\n", strip=True)
        for chunk in re.split(r"\n{1,}", text):
            chunk = _clean_text(chunk)
            if len(chunk) > 60 and not _SKIP_TEXT.match(chunk):
                emit({"kind": "para", "text": chunk[:4000]})

    return title, blocks


# ─── images ────────────────────────────────────────────────────────────────

def _load_image(source: str, deadline: float):
    """Return (png_bytes, width, height), or None if it is not worth placing.

    Everything is decoded and re-encoded rather than passed through: the web
    serves WebP and AVIF that ReportLab will not read, transparent PNGs that
    print as black, and CMYK JPEGs. Re-encoding to RGB PNG on a white ground
    makes all of them behave.
    """
    from PIL import Image as PILImage

    try:
        if source.startswith("data:"):
            import base64
            header, _, payload = source.partition(",")
            if "base64" not in header:
                return None
            data = base64.b64decode(payload + "===")
            if len(data) > MAX_IMAGE_BYTES:
                return None
        else:
            if not source.lower().startswith(("http://", "https://")):
                return None
            if source.lower().split("?")[0].endswith(".svg"):
                return None              # vector, and ReportLab cannot place it
            data, _, _ = _get(source, min(deadline, time.monotonic() + IMAGE_TIMEOUT),
                              "image/*", MAX_IMAGE_BYTES)
    except Exception:
        return None                      # a missing image never fails a capture

    try:
        image = PILImage.open(io.BytesIO(data))
        image.load()
        width, height = image.size
        if width < MIN_IMAGE_PIXELS or height < MIN_IMAGE_PIXELS:
            return None                  # icon, spacer or tracking pixel
        if width * height > 40_000_000:
            return None
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            ground = PILImage.new("RGB", image.size, (255, 255, 255))
            ground.paste(image, mask=image.split()[-1])
            image = ground
        elif image.mode != "RGB":
            image = image.convert("RGB")
        if width > 1600:                 # nothing on an A4 page needs more
            height = int(height * 1600 / width)
            width = 1600
            image = image.resize((width, height), PILImage.LANCZOS)
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        out.seek(0)
        return out, width, height
    except Exception:
        return None


# ─── the PDF ───────────────────────────────────────────────────────────────

DISCLAIMER = (
    "This is a capture of the content visible on the page at the time and date "
    "above. It is not a screenshot and not a copy of the live site: links are "
    "flat text and cannot be clicked, and menus, video, forms, scripted "
    "widgets and anything behind a sign-in do not appear. Check the source "
    "before relying on it."
)


def render(capture: Capture, deadline: float) -> io.BytesIO:
    """Lay the captured blocks out as an Impact Analytics branded PDF."""
    fonts = pdf_fonts.load()
    clean = fonts.clean

    page_w, page_h = A4
    margin = 17 * mm
    content_w = page_w - margin * 2
    band_h = 30 * mm

    def style(name, size, leading, colour=BLACK, font=None, **kwargs):
        return ParagraphStyle(name, fontName=font or fonts.regular,
                              fontSize=size, leading=leading, textColor=colour,
                              alignment=TA_LEFT, **kwargs)

    S = {
        1: style("h1", 16, 21, BLACK, fonts.bold, spaceBefore=12, spaceAfter=5),
        2: style("h2", 13, 18, BLACK, fonts.bold, spaceBefore=11, spaceAfter=4),
        3: style("h3", 11, 15, BLACK, fonts.bold, spaceBefore=9, spaceAfter=3),
        4: style("h4", 10, 14, BLUE, fonts.bold, spaceBefore=8, spaceAfter=3),
    }
    body = style("body", 9.6, 14.6, BLACK, spaceAfter=7)
    bullet = style("bullet", 9.6, 14.2, BLACK, spaceAfter=3, leftIndent=12,
                   bulletIndent=2)
    quote = style("quote", 10.4, 15.5, BLACK, fonts.italic, spaceAfter=8,
                  leftIndent=14, spaceBefore=4)
    code = style("code", 8.2, 11.5, BLACK, spaceAfter=8, leftIndent=8)
    caption = style("caption", 8.2, 11.5, GREY, spaceAfter=10)
    note = style("note", 8.4, 12.4, GREY, spaceAfter=0)
    cell = style("cell", 8.4, 11.5, BLACK)
    cell_head = style("cellhead", 8.4, 11.5, BLACK, fonts.bold)

    host = urlparse(capture.final_url).hostname or ""
    stamp = datetime.now(timezone.utc).strftime("%d %B %Y at %H:%M UTC")

    def decorate(canvas, doc):
        canvas.saveState()
        if doc.page == 1:
            canvas.setFillColor(FIELD)
            canvas.rect(0, page_h - band_h, page_w, band_h, stroke=0, fill=1)
            canvas.setStrokeColor(colors.Color(1, 1, 1, alpha=0.10))
            canvas.setLineWidth(0.4)
            for step in range(0, int(page_w), 34):
                canvas.line(step, page_h - band_h, step, page_h)
            canvas.setFillColor(colors.white)
            canvas.setFont(fonts.bold, 7.2)
            canvas.drawString(margin, page_h - 12 * mm, "PAGE CAPTURE")
            canvas.setFont(fonts.bold, 15)
            canvas.drawString(margin, page_h - 19 * mm,
                              _fit(canvas, capture.title, fonts.bold, 15,
                                   content_w, clean))
            canvas.setFont(fonts.regular, 7.6)
            canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.80))
            canvas.drawString(margin, page_h - 24.5 * mm,
                              _fit(canvas, capture.final_url, fonts.regular,
                                   7.6, content_w, clean))
        canvas.setFillColor(GREY)
        canvas.setFont(fonts.regular, 6.6)
        canvas.drawString(margin, 10 * mm, clean(
            f"Captured from {host} on {stamp}. Visible page content only."))
        canvas.drawRightString(page_w - margin, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=margin,
                          rightMargin=margin, topMargin=margin,
                          bottomMargin=margin, title=capture.title[:120],
                          author="Impact Analytics", subject=capture.final_url)
    doc.addPageTemplates([
        PageTemplate(id="first", onPage=decorate, frames=[
            Frame(margin, margin + 6 * mm, content_w,
                  page_h - band_h - margin - 6 * mm, id="f")]),
        PageTemplate(id="later", onPage=decorate, frames=[
            Frame(margin, margin + 6 * mm, content_w,
                  page_h - margin * 2 - 6 * mm, id="l")]),
    ])

    story: list = [Spacer(1, 8), _NoteBox(DISCLAIMER, content_w, note,
                                          OFF_WHITE, BLUE), Spacer(1, 12)]

    title_key = re.sub(r"\W+", "", capture.title).lower()[:60]
    for index, block in enumerate(capture.blocks):
        kind = block["kind"]
        if kind == "heading":
            # The band at the top already carries the title; the page's own h1
            # repeating it two centimetres lower just reads as a mistake.
            if (index < 3 and block["level"] == 1
                    and re.sub(r"\W+", "", block["text"]).lower()[:60] == title_key):
                continue
            story.append(Paragraph(clean(block["text"]), S[block["level"]]))
        elif kind == "para":
            story.append(Paragraph(clean(block["text"]), body))
        elif kind == "list":
            for index, item in enumerate(block["items"], 1):
                marker = f"{index}." if block.get("ordered") else "•"
                story.append(Paragraph(clean(item), bullet,
                                       bulletText=clean(marker)))
            story.append(Spacer(1, 6))
        elif kind == "quote":
            story.append(_QuoteRule(Paragraph(clean(block["text"]), quote),
                                    content_w, BLUE))
        elif kind == "code":
            lines = []
            for raw in block["text"].split("\n")[:60]:
                stripped = raw.lstrip(" \t")
                indent = "&nbsp;" * min(len(raw) - len(stripped), 24)
                lines.append(indent + clean(stripped))
            story.append(_CodeBox("<br/>".join(lines) or "&nbsp;",
                                  content_w, code))
        elif kind == "rule":
            story.append(_Rule(content_w, LINE))
        elif kind == "table":
            rows = block["rows"]
            data = [[Paragraph(clean(value), cell_head if not row else cell)
                     for value in cells] for row, cells in enumerate(rows)]
            width = content_w / max(len(rows[0]), 1)
            table = Table(data, colWidths=[width] * len(rows[0]), repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), OFF_WHITE),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(table)
            story.append(Spacer(1, 10))
        elif kind == "image" and block.get("data") is not None:
            width, height = block["size"]
            draw_w = min(content_w, width * 0.75)
            draw_h = draw_w * height / width
            if draw_h > 190 * mm:                 # never let one image own a page
                draw_h = 190 * mm
                draw_w = draw_h * width / height
            picture = RLImage(block["data"], width=draw_w, height=draw_h)
            picture.hAlign = "LEFT"
            parts = [picture]
            if block.get("alt"):
                parts += [Spacer(1, 4),
                          Paragraph(clean(block["alt"][:300]), caption)]
            else:
                parts.append(Spacer(1, 10))
            # Hold a picture and its caption together only when they are small
            # enough to move as a unit. Doing it for a tall image just pushes
            # the whole thing to the next page and leaves a hole behind it.
            if draw_h < 100 * mm:
                story.append(KeepTogether(parts))
            else:
                story.extend(parts)

    if capture.truncated:
        story.append(Spacer(1, 8))
        story.append(Paragraph(clean(
            "The page continued past the capture limit and was cut off here."),
            caption))
    if len(story) <= 3:
        raise CaptureError(
            "No readable content was found on that page. It is probably built "
            "entirely in JavaScript, or behind a sign-in.")

    doc.build(story)
    buffer.seek(0)
    return buffer


def _fit(canvas, text, font, size, width, clean):
    """Trim a single line to the width available, with an ellipsis."""
    value = clean(text)
    if canvas.stringWidth(value, font, size) <= width:
        return value
    while value and canvas.stringWidth(value + "...", font, size) > width:
        value = value[:-1]
    return value + "..."


def _NoteBox(text: str, width: float, style, background, accent):
    """A tinted panel with an accent rule. A Table rather than a custom
    flowable so long text still paginates properly."""
    table = Table([[Paragraph(pdf_fonts.load().clean(text), style)]],
                  colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return table


def _QuoteRule(paragraph, width: float, accent):
    table = Table([[paragraph]], colWidths=[width])
    table.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, -1), 2, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _CodeBox(markup: str, width: float, style):
    """Preformatted text keeps its shape, on a tint so it reads as code."""
    table = Table([[Paragraph(markup, style)]], colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), OFF_WHITE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _Rule(width: float, colour):
    table = Table([[""]], colWidths=[width], rowHeights=[1])
    table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, colour),
                               ("TOPPADDING", (0, 0), (-1, -1), 8),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return table


# ─── putting it together ───────────────────────────────────────────────────

def capture(url: str, with_images: bool = True) -> tuple[io.BytesIO, str]:
    """Fetch a page and return (pdf, title). Raises CaptureError with a
    message the person who pasted the link can act on."""
    if not Config.ALLOW_REMOTE_FETCH:
        raise CaptureError("Remote fetching is disabled on this deployment.")

    target = normalise(url)
    deadline = time.monotonic() + TOTAL_BUDGET
    data, final_url, content_type = _get(
        target, deadline,
        "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        MAX_HTML_BYTES)

    # A link straight to a PDF is already the thing being asked for. Handing
    # back a re-typeset copy of it would be worse than the original.
    if "application/pdf" in content_type or data[:5] == b"%PDF-":
        name = urlparse(final_url).path.rsplit("/", 1)[-1] or "page"
        return io.BytesIO(data), name.removesuffix(".pdf")

    if not ("html" in content_type or "xml" in content_type
            or data[:512].lstrip()[:1] == b"<"):
        raise CaptureError(
            "That link is a file, not a web page. Add it to the library "
            "instead, where files are parsed and indexed.")

    title, blocks = extract(_decode(data, content_type), final_url)
    truncated = len(blocks) > 900
    blocks = blocks[:900]

    if with_images:
        budget = 0
        for block in blocks:
            if block["kind"] != "image":
                continue
            if budget >= MAX_IMAGES or time.monotonic() > deadline - 8:
                block["kind"] = "skipped-image"
                continue
            loaded = _load_image(block["src"], deadline)
            if loaded is None:
                block["kind"] = "skipped-image"
                continue
            block["data"], size = loaded[0], (loaded[1], loaded[2])
            block["size"] = size
            budget += 1
    else:
        for block in blocks:
            if block["kind"] == "image":
                block["kind"] = "skipped-image"

    result = Capture(url=target, final_url=final_url, title=title,
                     blocks=[b for b in blocks if b["kind"] != "skipped-image"],
                     truncated=truncated)
    return render(result, deadline), title


def filename_for(title: str, url: str) -> str:
    """A filename a person will recognise in their downloads folder."""
    base = re.sub(r"[^A-Za-z0-9]+", "-", title or "").strip("-")
    if len(base) < 3:
        base = re.sub(r"[^A-Za-z0-9]+", "-",
                      urlparse(url).hostname or "page").strip("-")
    return (base[:70] or "page") + ".pdf"
