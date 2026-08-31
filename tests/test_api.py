"""API contract tests, including the behaviours that were broken before."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def client(monkeypatch):
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    monkeypatch.setenv("CIQ_DB_PATH", path)
    monkeypatch.setenv("CIQ_ADMIN_PASSCODE", "testpass")
    monkeypatch.setenv("CIQ_SECRET_KEY", "test-secret")

    for module in ("ciq.config", "ciq.db", "ciq.llm", "app"):
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


def add(client, **fields):
    payload = {"competitor": "o9", "title": "T", "category": "battlecard"}
    payload.update(fields)
    return client.post("/api/entries", data=payload,
                       content_type="multipart/form-data")


def test_health_reports_database_state(client):
    body = client.get("/healthz").get_json()
    assert body["ok"] is True
    assert body["entries"] == 0


def test_entry_requires_a_competitor(client):
    assert add(client, competitor="").status_code == 400


def test_entry_requires_some_source(client):
    response = add(client, note="")
    assert response.status_code == 400
    assert "file" in response.get_json()["error"].lower()


def test_unknown_category_is_rejected(client):
    assert add(client, category="nonsense", note="n").status_code == 400


def test_create_then_search_roundtrip(client):
    assert add(client, note="Enterprise planning").status_code == 201
    body = client.get("/api/search?q=o9 battlecard").get_json()
    assert body["total"] == 1
    assert body["intent"]["competitor"] == "o9 Solutions"


def test_delete_is_reflected_in_search(client):
    entry_id = add(client, note="n").get_json()["entry"]["id"]
    assert client.delete(f"/api/entries/{entry_id}").status_code == 200
    assert client.get("/api/search?q=o9").get_json()["total"] == 0


def test_missing_entry_returns_404(client):
    assert client.get("/api/entries/nope").status_code == 404


def test_ai_endpoints_report_unavailable_rather_than_failing_silently(client):
    """The prototype returned 401 from the browser with no explanation. With no
    key configured the server must say so plainly."""
    entry_id = add(client, note="Some competitor content here.").get_json()["entry"]["id"]
    response = client.post(f"/api/entries/{entry_id}/analyze")
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.get_json()["error"]


def test_admin_routes_require_authentication(client):
    assert client.get("/api/admin/export").status_code == 403
    assert client.post("/api/admin/clear").status_code == 403


def test_admin_rejects_a_wrong_passcode(client):
    response = client.post("/api/admin/login", json={"passcode": "wrong"})
    assert response.status_code == 401


def test_admin_unlocks_with_the_right_passcode(client):
    assert client.post("/api/admin/login",
                       json={"passcode": "testpass"}).status_code == 200
    assert client.get("/api/admin/export").status_code == 200


def test_import_accepts_the_prototype_export_format(client):
    """The old app exported base64 fileData. That library must import cleanly."""
    import base64
    payload = [{
        "id": "smpl02", "competitor": "Blue Yonder",
        "title": "Blue Yonder Overview", "category": "information",
        "note": "Mature suite.",
        "fileData": base64.b64encode(
            b"Weaknesses: legacy architecture and long timelines.").decode(),
        "fileName": "by.txt", "fileUrl": "", "lovable": "",
        "addedAt": "2026-06-24T10:05:00Z",
    }]
    client.post("/api/admin/login", json={"passcode": "testpass"})
    data = {"file": (__import__("io").BytesIO(json.dumps(payload).encode()),
                     "library.json")}
    response = client.post("/api/admin/import", data=data,
                           content_type="multipart/form-data")
    assert response.get_json()["imported"] == 1
    # The base64 body must be indexed, not just stored.
    found = client.get("/api/search?q=legacy architecture").get_json()
    assert found["total"] == 1
