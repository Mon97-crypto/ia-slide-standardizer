"""Tests for turning a web page into a PDF.

Two things here are worth more than the feature itself. The URL is supplied by
a user and fetched by the server, so the guard against reaching private
addresses is a security boundary, not a nicety. And the page is written by
someone else, so the renderer has to survive markup and characters nobody on
this side chose.
"""
from __future__ import annotations

import http.server
import os
import socket
import sys
import tempfile
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ciq import page_capture as pc          # noqa: E402
from ciq.page_capture import CaptureError    # noqa: E402


# ─── a page to capture ─────────────────────────────────────────────────────

ARTICLE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>o9 launches agentic planning | Retail Weekly</title></head><body>
<div id="cookie-consent"><p>We use cookies.</p><button>Accept all</button></div>
<header><nav><ul><li><a href="/">Home</a></li></ul></nav></header>
<main><article class="entry-content">
  <h1>o9 launches agentic planning</h1>
  <div class="social-share"><a href="#">Tweet this</a></div>
  <p>o9 announced an &ldquo;agentic&rdquo; extension &mdash; aimed at retailers.</p>
  <h2>What is new</h2>
  <ul><li>Autonomous replenishment</li><li>A planner console</li></ul>
  <table><tr><th>Dimension</th><th>o9</th></tr>
         <tr><td>Time to value</td><td>9&ndash;14 months</td></tr></table>
  <blockquote>Impressive in a demo.</blockquote>
  <img src="spacer.gif" data-src="wide.png" alt="The console">
  <p>Impact Analytics declined to comment.</p>
</article>
<aside class="related-posts"><p>Read next: Blue Yonder Q3</p></aside>
<section id="comments"><p>Great article!</p></section></main>
<aside class="widget newsletter-signup"><p>Subscribe for the weekly briefing.</p></aside>
<footer><p>Copyright 2026 Retail Weekly</p></footer>
</body></html>"""


def _png(width: int, height: int) -> bytes:
    import io

    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (38, 75, 215)).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def site():
    """A local site to capture, so the tests need no internet."""
    directory = tempfile.mkdtemp()
    files = {
        "index.html": ARTICLE.encode(),
        "wide.png": _png(900, 500),
        "tiny.png": _png(20, 20),
        "paper.pdf": b"%PDF-1.4\n% a real pdf would follow\n%%EOF\n",
        "sheet.csv": b"a,b\n1,2\n",
        "empty.html": b"<html><body><div><span>hi</span></div></body></html>",
        "divs.html": ("<html><body><div id='content'>" +
                      "".join(f"<div>{'Sentence about the market. ' * 6}</div>"
                              for _ in range(4)) +
                      "</div></body></html>").encode(),
    }
    for name, data in files.items():
        with open(os.path.join(directory, name), "wb") as handle:
            handle.write(data)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def do_GET(self):
            if self.path.startswith("/bounce-private"):
                self.send_response(302)
                self.send_header("Location", "http://10.1.2.3/secret")
                self.end_headers()
                return
            if self.path.startswith("/gone"):
                self.send_response(404)
                self.end_headers()
                return
            return super().do_GET()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture()
def reachable(monkeypatch):
    """Let the tests talk to the local site.

    The guard refuses loopback, which is exactly right in production and
    exactly wrong for a test server. It is exercised directly below instead.
    """
    monkeypatch.setattr(pc, "assert_public",
                        lambda host: None if host in ("127.0.0.1", "localhost")
                        else pytest.fail(f"unexpected host {host}"))
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("no_proxy", "*")


# ─── the URL, before anything is fetched ───────────────────────────────────

def test_a_bare_domain_is_treated_as_https():
    assert pc.normalise("example.com/news") == "https://example.com/news"
    assert pc.normalise("  https://example.com  ") == "https://example.com"


@pytest.mark.parametrize("url,reason", [
    ("", "Paste a link"),
    ("   ", "Paste a link"),
    ("file:///etc/passwd", "http and https"),
    ("gopher://example.com", "http and https"),
    ("javascript:alert(1)", "http and https"),
    ("data:text/html,<h1>x", "http and https"),
    # Credentials in a URL are a standard way to talk to an internal service.
    ("https://admin:hunter2@example.com", "credentials"),
    ("https://" + "a" * 2100, "too long"),
])
def test_links_that_are_refused_before_a_request_is_made(url, reason):
    with pytest.raises(CaptureError, match=reason):
        pc.normalise(url)


# ─── the address it resolves to ────────────────────────────────────────────

def _resolves_to(monkeypatch, *addresses):
    def fake(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
                for address in addresses]
    monkeypatch.setattr(pc.socket, "getaddrinfo", fake)


@pytest.mark.parametrize("address", [
    "127.0.0.1",            # loopback
    "10.1.2.3",             # RFC1918
    "192.168.0.10",
    "172.16.9.9",
    "169.254.169.254",      # the cloud metadata service
    "100.64.0.1",           # carrier grade NAT, used for internal meshes
    "0.0.0.0",
    "::1",
    "fd00::1",              # unique local
])
def test_an_address_off_the_public_internet_is_refused(monkeypatch, address):
    """This endpoint fetches a URL a user chose, from inside the deployment.
    Without this check it is a window onto the private network."""
    _resolves_to(monkeypatch, address)
    with pytest.raises(CaptureError, match="private network"):
        pc.assert_public("intranet.example.com")


def test_a_public_address_is_allowed(monkeypatch):
    _resolves_to(monkeypatch, "93.184.216.34")
    pc.assert_public("example.com")


def test_a_name_answering_with_both_is_refused(monkeypatch):
    """Every answer is checked, not just the first, so a name that mixes a
    public address with a private one cannot slip the private one through."""
    _resolves_to(monkeypatch, "93.184.216.34", "10.0.0.5")
    with pytest.raises(CaptureError, match="private network"):
        pc.assert_public("mixed.example.com")


def test_a_name_that_does_not_resolve_says_so(monkeypatch):
    def fake(*args, **kwargs):
        raise socket.gaierror("nope")
    monkeypatch.setattr(pc.socket, "getaddrinfo", fake)
    with pytest.raises(CaptureError, match="Could not find"):
        pc.assert_public("no-such-host.example")


def test_a_redirect_into_private_space_is_refused(site, monkeypatch):
    """The first hop being public says nothing about the second, so the check
    runs again on every hop rather than once at the start."""
    checked = []

    def guard(host):
        checked.append(host)
        if host not in ("127.0.0.1", "localhost"):
            raise CaptureError("That address is on a private network.")
    monkeypatch.setattr(pc, "assert_public", guard)
    monkeypatch.setenv("no_proxy", "*")
    with pytest.raises(CaptureError, match="private network"):
        pc.capture(f"{site}/bounce-private")
    assert "10.1.2.3" in checked


# ─── reading the page ──────────────────────────────────────────────────────

def _blocks(html, base="https://example.com/a"):
    return pc.extract(html, base)[1]


def test_the_parts_a_reader_saw_are_kept_in_order():
    title, blocks = pc.extract(ARTICLE, "https://example.com/a")
    assert title == "o9 launches agentic planning | Retail Weekly"
    kinds = [b["kind"] for b in blocks]
    assert kinds.index("heading") < kinds.index("list") < kinds.index("table")
    text = " ".join(b.get("text", "") for b in blocks)
    assert "agentic" in text and "declined to comment" in text
    assert any(b["kind"] == "quote" for b in blocks)
    assert [b for b in blocks if b["kind"] == "table"][0]["rows"][0][0] == "Dimension"


@pytest.mark.parametrize("gone", [
    "Accept all", "Home", "Tweet this", "Read next", "Great article",
    "Subscribe for the weekly", "Copyright 2026",
])
def test_page_furniture_does_not_reach_the_pdf(gone):
    """A capture people trust is the article, not the site's navigation,
    cookie banner, share buttons, comments and newsletter box."""
    blocks = _blocks(ARTICLE)
    body = " ".join(str(b.get("text", "")) + " ".join(b.get("items", []))
                    for b in blocks)
    assert gone.lower() not in body.lower()


def test_a_lazy_loaded_image_resolves_to_the_real_file():
    """src is a placeholder on most modern sites; reading it naively collects
    grey spacers instead of the page's pictures."""
    images = [b for b in _blocks(ARTICLE) if b["kind"] == "image"]
    assert images and images[0]["src"] == "https://example.com/wide.png"


def test_srcset_picks_a_usable_size():
    html = ('<article><p>x</p><img srcset="/i/small.png 48w, /i/large.png 900w" '
            'alt="a"></article>')
    images = [b for b in _blocks(html) if b["kind"] == "image"]
    assert images[0]["src"] == "https://example.com/i/large.png"


def test_a_repeated_headline_is_printed_once():
    html = ("<article><h1>Same headline</h1><h1>Same headline</h1>"
            "<p>" + "Body text. " * 20 + "</p></article>")
    headings = [b for b in _blocks(html) if b["kind"] == "heading"]
    assert len(headings) == 1


def test_a_page_built_from_bare_divs_still_yields_text():
    """Plenty of sites never use a <p>. Descending past them and returning
    nothing would produce an empty PDF with no explanation."""
    html = "<div id='content'>" + "".join(
        f"<div>{'A sentence about the market. ' * 5}</div>" for _ in range(4)
    ) + "</div>"
    paras = [b for b in _blocks(html) if b["kind"] == "para"]
    assert len(paras) >= 1
    assert "market" in paras[0]["text"]


def test_broken_markup_does_not_raise():
    for html in ("<article><p>unclosed", "", "<html>", "<article><table><tr>",
                 "<div><div><div>" * 40 + "deep"):
        pc.extract(html, "https://example.com/a")


# ─── the rendered file ─────────────────────────────────────────────────────

def test_a_page_becomes_a_readable_pdf(site, reachable):
    import pypdf
    buffer, title = pc.capture(f"{site}/index.html")
    data = buffer.getvalue()
    assert data[:5] == b"%PDF-"
    reader = pypdf.PdfReader(buffer)
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "agentic" in text
    assert "Autonomous replenishment" in text          # the list
    assert "Time to value" in text                     # the table
    assert "Visible page content only" in text         # the footer
    assert "cannot be clicked" in text                 # the disclaimer
    assert title.startswith("o9 launches")


def test_the_disclaimer_is_on_the_document_itself(site, reachable):
    """It travels: the person who is forwarded the PDF never saw the page it
    was made from, and needs to know what is missing from it."""
    import pypdf
    buffer, _ = pc.capture(f"{site}/index.html")
    first = pypdf.PdfReader(buffer).pages[0].extract_text()
    assert "not a screenshot" in first
    assert "cannot be clicked" in first
    assert "behind a sign-in" in first


def test_characters_the_font_cannot_draw_never_reach_the_page():
    """Outside its coverage a font draws a solid black box instead of failing,
    so a page with CJK or emoji would come back looking corrupted."""
    from ciq import pdf_fonts
    fonts = pdf_fonts.load()
    cleaned = fonts.clean("Café “o9” — 中文 🙂 <b> & ≥50%")
    assert "&lt;b&gt;" in cleaned and "&amp;" in cleaned
    assert "中" not in cleaned and "🙂" not in cleaned
    assert "Café" in cleaned
    for char in cleaned:
        assert fonts._covers(char), f"{char!r} is not in the font"


def test_an_image_too_small_to_be_content_is_skipped(site, reachable):
    assert pc._load_image(f"{site}/tiny.png", pc.time.monotonic() + 10) is None
    assert pc._load_image(f"{site}/wide.png", pc.time.monotonic() + 10) is not None


def test_a_missing_image_does_not_fail_the_capture(site, reachable):
    assert pc._load_image(f"{site}/no-such.png", pc.time.monotonic() + 10) is None


def test_a_page_with_nothing_on_it_says_so(site, reachable):
    with pytest.raises(CaptureError, match="No readable content"):
        pc.capture(f"{site}/empty.html")


def test_a_link_to_a_pdf_is_passed_straight_through(site, reachable):
    """Re-typesetting a PDF would be strictly worse than the original."""
    buffer, title = pc.capture(f"{site}/paper.pdf")
    assert buffer.getvalue().startswith(b"%PDF-1.4")
    assert title == "paper"


def test_a_link_to_a_data_file_is_refused(site, reachable):
    with pytest.raises(CaptureError, match="a file, not a web page"):
        pc.capture(f"{site}/sheet.csv")


def test_a_missing_page_reports_the_status(site, reachable):
    with pytest.raises(CaptureError, match="not found"):
        pc.capture(f"{site}/gone")


def test_the_filename_is_recognisable():
    assert pc.filename_for("o9 Solutions — Pricing", "x") == "o9-Solutions-Pricing.pdf"
    assert pc.filename_for("", "https://www.o9solutions.com/x") == "www-o9solutions-com.pdf"
    assert pc.filename_for("中文", "https://a.co") == "a-co.pdf"


# ─── the route ─────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    monkeypatch.setenv("CIQ_DB_PATH", path)
    monkeypatch.setenv("CIQ_SECRET_KEY", "test-secret")
    for module in [m for m in list(sys.modules)
                   if m == "ciq" or m.startswith("ciq.")] + ["app"]:
        sys.modules.pop(module, None)
    import app as application
    application.app.config["TESTING"] = True
    with application.app.test_client() as test_client:
        yield test_client
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except OSError:
            pass


def test_the_route_returns_a_pdf(client, site, monkeypatch):
    from ciq import page_capture
    monkeypatch.setattr(page_capture, "assert_public", lambda host: None)
    monkeypatch.setenv("no_proxy", "*")
    response = client.post("/api/page.pdf", json={"url": f"{site}/index.html"})
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data[:5] == b"%PDF-"
    assert "o9-launches" in response.headers["Content-Disposition"]


def test_the_route_can_skip_images(client, site, monkeypatch):
    from ciq import page_capture
    monkeypatch.setattr(page_capture, "assert_public", lambda host: None)
    monkeypatch.setenv("no_proxy", "*")
    with_images = client.post("/api/page.pdf",
                              json={"url": f"{site}/index.html"}).data
    without = client.post("/api/page.pdf",
                          json={"url": f"{site}/index.html",
                                "images": False}).data
    assert len(without) < len(with_images)


@pytest.mark.parametrize("url,reason", [
    ("", "Paste a link"),
    ("file:///etc/passwd", "http and https"),
    ("http://admin:pw@example.com", "credentials"),
])
def test_the_route_refuses_a_bad_link_as_json(client, url, reason):
    """The browser parses every response as JSON, so a refusal has to be JSON
    and not an HTML error page."""
    response = client.post("/api/page.pdf", json={"url": url})
    assert response.status_code == 400
    assert response.mimetype == "application/json"
    assert reason.lower() in response.get_json()["error"].lower()


def test_the_route_refuses_a_private_address(client, monkeypatch):
    """The end to end version of the guard: a link aimed at the deployment's
    own network is refused by the endpoint, not merely by a helper."""
    _resolves_to(monkeypatch, "169.254.169.254")   # the metadata service
    response = client.post("/api/page.pdf",
                           json={"url": "http://metadata.example.com/"})
    assert response.status_code == 400
    assert "private network" in response.get_json()["error"]


def test_the_pictures_on_the_page_reach_the_pdf(site, reachable):
    """A capture without the page's images loses most of what a product or
    launch page was actually saying."""
    import pypdf
    buffer, _ = pc.capture(f"{site}/index.html")
    embedded = sum(len(list(page.images))
                   for page in pypdf.PdfReader(buffer).pages)
    assert embedded >= 1
    plain, _ = pc.capture(f"{site}/index.html", with_images=False)
    assert sum(len(list(page.images))
               for page in pypdf.PdfReader(plain).pages) == 0
