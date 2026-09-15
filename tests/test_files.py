"""Tests for keeping and serving the original documents.

The library used to keep only the text extracted from an upload, which made
every entry searchable and none of them openable. These cover the document
being kept, handed back correctly, and handed back safely: this origin holds
the session cookie, so what it will render inline is a security decision.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ciq import files                        # noqa: E402

def _pptx() -> bytes:
    """A real deck. Extraction rejects anything that is not one, so a stand-in
    would only prove the upload path rejects rubbish."""
    from pptx import Presentation
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Blue Yonder head to head"
    buffer = io.BytesIO()
    deck.save(buffer)
    return buffer.getvalue()


def _pdf() -> bytes:
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    page.drawString(72, 720, "Quarterly competitor brief")
    page.save()
    return buffer.getvalue()


PPTX = _pptx()
PDF = _pdf()


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


def upload(client, data=b"Competitor pricing notes.", name="notes.txt",
           **fields):
    payload = {"competitor": "o9", "title": "T", "category": "battlecard",
               **fields}
    if data is not None:
        payload["file"] = (io.BytesIO(data), name)
    response = client.post("/api/entries", data=payload,
                           content_type="multipart/form-data")
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["entry"]


# ─── naming and types ──────────────────────────────────────────────────────

@pytest.mark.parametrize("name,mime", [
    ("deck.pptx", "application/vnd.openxmlformats-officedocument."
                  "presentationml.presentation"),
    ("report.PDF", "application/pdf"),
    ("sheet.xlsx", "application/vnd.openxmlformats-officedocument."
                   "spreadsheetml.sheet"),
    ("notes.md", "text/plain"),
    ("mystery.bin", "application/octet-stream"),
    ("", "application/octet-stream"),
])
def test_the_type_comes_from_the_extension(name, mime):
    assert files.mime_for(name) == mime


@pytest.mark.parametrize("name", ["page.html", "logo.svg", "x.xhtml", "a.htm"])
def test_markup_is_never_rendered_in_place(name):
    """Inline on this origin, script in an uploaded file would run with the
    signed-in user's session. These download instead."""
    assert not files.opens_in_browser(files.mime_for(name))


@pytest.mark.parametrize("raw,expected", [
    ("../../etc/passwd", "passwd"),
    ("C:\\\\Users\\\\me\\\\deck.pptx", "deck.pptx"),
    ('quote"name.txt', "quotename.txt"),
    ("line\nbreak.txt", "linebreak.txt"),
    ("   ", "document"),
    ("", "document"),
])
def test_a_filename_cannot_escape_its_header_or_its_folder(raw, expected):
    assert files.safe_name(raw) == expected


# ─── keeping the document ──────────────────────────────────────────────────

def test_an_uploaded_file_can_be_opened_again(client):
    entry = upload(client, PPTX, "Q3 Deck.pptx")
    assert entry["has_file"] is True
    response = client.get(f"/api/entries/{entry['id']}/file")
    assert response.status_code == 200
    assert response.data == PPTX            # byte for byte, not the text
    assert "Q3 Deck.pptx" in response.headers["Content-Disposition"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_a_pdf_opens_in_the_browser_and_a_deck_downloads(client):
    reading = upload(client, PDF, "brief.pdf")
    deck = upload(client, PPTX, "deck.pptx")
    assert "inline" in client.get(
        f"/api/entries/{reading['id']}/file").headers["Content-Disposition"]
    assert "attachment" in client.get(
        f"/api/entries/{deck['id']}/file").headers["Content-Disposition"]


def test_markup_stored_as_a_document_still_downloads(client):
    """The check has to hold through the route, not only in the helper. HTML
    cannot be uploaded, but it can be attached, so it can reach the store."""
    entry = upload(client, None, note="x")
    client.post(f"/api/entries/{entry['id']}/file",
                data={"file": (io.BytesIO(b"<script>alert(1)</script>"),
                               "notes.html")},
                content_type="multipart/form-data")
    response = client.get(f"/api/entries/{entry['id']}/file")
    assert "attachment" in response.headers["Content-Disposition"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "text/html" not in response.headers["Content-Type"]


def test_every_listing_says_which_entries_hold_a_file(client):
    with_file = upload(client, PPTX, "deck.pptx")
    note_only = upload(client, None, note="Just a note.")
    listed = {e["id"]: e for e in client.get("/api/entries").get_json()["entries"]}
    assert listed[with_file["id"]]["has_file"] is True
    assert listed[note_only["id"]]["has_file"] is False
    found = {e["id"]: e for e in
             client.get("/api/search?q=o9").get_json()["results"]}
    assert found[with_file["id"]]["has_file"] is True


def test_deleting_an_entry_takes_its_file_with_it(client):
    entry = upload(client, PPTX, "deck.pptx")
    client.delete(f"/api/entries/{entry['id']}")
    assert client.get(f"/api/entries/{entry['id']}/file").status_code == 404


def test_clearing_the_library_leaves_no_files_behind(client):
    import app as application
    from ciq import db
    entry = upload(client, PPTX, "deck.pptx")
    db.clear_all(application.store())
    assert db.get_file(application.store(), entry["id"]) is None


# ─── entries whose file was never kept ─────────────────────────────────────

def test_the_extracted_text_opens_when_the_file_is_not_held(client):
    """Everything added before files were kept, and every note, still has to
    be openable, or the library has entries nobody can read."""
    entry = upload(client, None, note="Deal notes from the Q3 review.")
    assert entry["has_file"] is False
    response = client.get(f"/api/entries/{entry['id']}/text")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    # One charset, not two: passing a full type to send_file made Werkzeug
    # append a second one and the header came out malformed.
    assert response.headers["Content-Type"].count("charset") == 1
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    body = response.get_data(as_text=True)
    assert "Deal notes from the Q3 review." in body
    assert "T" in body                       # the title, as a heading


def test_asking_for_a_file_that_was_never_kept_explains_itself(client):
    entry = upload(client, None, note="A note.")
    response = client.get(f"/api/entries/{entry['id']}/file")
    assert response.status_code == 404
    assert "extracted text" in response.get_json()["error"]


def test_a_missing_entry_is_a_404_not_a_crash(client):
    for path in ("file", "text"):
        assert client.get(f"/api/entries/nope/{path}").status_code == 404


# ─── putting a document back ───────────────────────────────────────────────

def test_a_file_can_be_attached_to_an_older_entry(client):
    """The fix for a library that predates this: the entry keeps its id, its
    analysis and its place, and gains the document."""
    entry = upload(client, None, note="Only a note was saved.")
    response = client.post(f"/api/entries/{entry['id']}/file",
                           data={"file": (io.BytesIO(PPTX), "recovered.pptx")},
                           content_type="multipart/form-data")
    assert response.status_code == 200
    assert response.get_json()["entry"]["has_file"] is True
    served = client.get(f"/api/entries/{entry['id']}/file")
    assert served.data == PPTX
    assert "recovered.pptx" in served.headers["Content-Disposition"]


def test_attaching_indexes_a_file_that_had_no_text(client):
    entry = upload(client, None, note="x")
    client.post(f"/api/entries/{entry['id']}/file",
                data={"file": (io.BytesIO(b"Blue Yonder markdown pricing tiers."),
                               "pricing.txt")},
                content_type="multipart/form-data")
    found = client.get("/api/search?q=markdown pricing tiers").get_json()
    assert entry["id"] in [r["id"] for r in found["results"]]


def test_attaching_does_not_rewrite_text_that_came_from_a_document(client):
    """Replacing indexed text would quietly change what searches, analyses and
    battlecards were built on."""
    entry = upload(client, b"The original extracted content.", "original.txt")
    client.post(f"/api/entries/{entry['id']}/file",
                data={"file": (io.BytesIO(b"Something else entirely."),
                               "replacement.txt")},
                content_type="multipart/form-data")
    after = client.get(f"/api/entries/{entry['id']}").get_json()["entry"]
    assert after["content"] == "The original extracted content."


@pytest.mark.parametrize("data,reason", [
    (None, "Choose a file"),
    (b"", "empty"),
])
def test_attaching_nothing_is_refused(client, data, reason):
    entry = upload(client, None, note="x")
    payload = {} if data is None else {"file": (io.BytesIO(data), "empty.txt")}
    response = client.post(f"/api/entries/{entry['id']}/file", data=payload,
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert reason.lower() in response.get_json()["error"].lower()
