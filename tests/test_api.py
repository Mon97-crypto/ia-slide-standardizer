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

    # Drop the ciq package itself, not just its submodules. "from ciq import
    # llm" resolves through the package attribute, which outlives a submodule
    # being popped from sys.modules. Leaving it in place hands the app one
    # module object while a test patches another, and the patch silently
    # misses.
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


def test_battlecard_requires_a_competitor(client):
    assert client.post("/api/battlecard", json={"competitor": ""}).status_code == 400


def test_battlecard_reports_unavailable_without_a_key(client):
    add(client, note="Blue Yonder has legacy architecture and long timelines.",
        competitor="Blue Yonder", title="BY notes", category="information")
    response = client.post("/api/battlecard", json={"competitor": "jda"})
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.get_json()["error"]


def test_selftest_requires_admin(client):
    assert client.post("/api/admin/selftest").status_code == 403


def test_selftest_reports_a_missing_key_without_calling_out(client):
    """With no key the report must explain the gap rather than error."""
    client.post("/api/admin/login", json={"passcode": "testpass"})
    report = client.post("/api/admin/selftest").get_json()["report"]
    assert report["ok"] is False
    assert report["key_present"] is False
    assert "ANTHROPIC_API_KEY" in report["checks"][0]["error"]


def test_selftest_never_returns_the_key(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value")
    client.post("/api/admin/login", json={"passcode": "testpass"})
    body = client.post("/api/admin/selftest").get_data(as_text=True)
    assert "sk-ant-secret-value" not in body


def test_healthz_reports_where_the_key_came_from(client):
    body = client.get("/healthz").get_json()
    assert body["key_source"] == "missing"
    assert body["ai_enabled"] is False


def test_keycheck_requires_admin(client):
    assert client.get("/api/admin/keycheck").status_code == 403


def test_keycheck_explains_a_missing_key_without_leaking_values(
        client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_LOOKALIKE_API_KEY", "sk-ant-should-not-appear")
    client.post("/api/admin/login", json={"passcode": "testpass"})
    response = client.get("/api/admin/keycheck")
    body = response.get_data(as_text=True)
    diagnostics = response.get_json()["diagnostics"]
    assert diagnostics["source"] == "missing"
    # The lookalike name is surfaced so a typo is visible, the value is not.
    assert "ANTHROPIC_LOOKALIKE_API_KEY" in diagnostics[
        "related_variable_names_present"]
    assert "sk-ant-should-not-appear" not in body


def test_a_key_in_a_secret_file_is_found(client, monkeypatch, tmp_path):
    """Render Secret Files mount on disk and never reach os.environ. A key put
    there must still switch AI on."""
    import ciq.config
    (tmp_path / "ANTHROPIC_API_KEY").write_text("sk-ant-from-a-secret-file\n")
    monkeypatch.setattr(ciq.config.Config, "SECRET_FILE_DIR", str(tmp_path))
    assert ciq.config.Config.ai_enabled() is True
    assert ciq.config.Config.api_key_with_source()[1] == "secret_file"
    # Surrounding whitespace from the file must not reach the API header.
    assert ciq.config.Config.api_key() == "sk-ant-from-a-secret-file"


def test_battlecard_without_research_skips_the_research_call(client, monkeypatch):
    """research=false must not reach for the network at all."""
    import ciq.llm as llm
    called = {"research": False}

    def fake_research(*args, **kwargs):
        called["research"] = True
        raise AssertionError("research should not run")

    monkeypatch.setattr(llm, "research_competitor", fake_research)
    add(client, note="Blue Yonder has legacy architecture.",
        competitor="Blue Yonder", title="BY", category="information")
    response = client.post("/api/battlecard",
                           json={"competitor": "jda", "research": False})
    assert called["research"] is False
    assert response.status_code == 503          # no key, but research was skipped


def test_a_research_failure_still_produces_a_card(client, monkeypatch):
    """Research is an enhancement. Losing it must not lose the battlecard."""
    import ciq.llm as llm

    monkeypatch.setattr(llm, "research_competitor", lambda *a, **k: (_ for _ in ()).throw(
        llm.LLMUnavailable("search is down")))
    monkeypatch.setattr(llm, "build_battlecard",
                        lambda competitor, passages, research: {
                            "competitor": competitor, "scorecard": [],
                            "researched": bool(research)})
    add(client, note="Blue Yonder notes.", competitor="Blue Yonder",
        title="BY", category="information")
    body = client.post("/api/battlecard", json={"competitor": "jda"}).get_json()
    assert body["ok"] is True
    assert "search is down" in body["research_error"]
    assert body["battlecard"]["researched"] is False
