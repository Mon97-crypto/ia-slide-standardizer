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


def test_library_tools_are_reachable_without_a_passcode(client):
    """The shared passcode is gone. Access control is Google sign-in, covered
    in tests/test_auth.py; with sign-in unconfigured these fall open."""
    assert client.get("/api/library/export").status_code == 200
    assert client.post("/api/library/clear").status_code == 200


def test_the_old_passcode_routes_no_longer_exist(client):
    assert client.post("/api/admin/login", json={"passcode": "impact"}).status_code == 404
    assert client.get("/api/admin/export").status_code == 404


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
    data = {"file": (__import__("io").BytesIO(json.dumps(payload).encode()),
                     "library.json")}
    response = client.post("/api/library/import", data=data,
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


def test_selftest_reports_a_missing_key_without_calling_out(client):
    """With no key the report must explain the gap rather than error."""
    report = client.post("/api/selftest").get_json()["report"]
    assert report["ok"] is False
    assert report["key_present"] is False
    assert "ANTHROPIC_API_KEY" in report["checks"][0]["error"]


def test_selftest_never_returns_the_key(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value")
    body = client.post("/api/selftest").get_data(as_text=True)
    assert "sk-ant-secret-value" not in body


def test_healthz_reports_where_the_key_came_from(client):
    body = client.get("/healthz").get_json()
    assert body["key_source"] == "missing"
    assert body["ai_enabled"] is False


def test_keycheck_explains_a_missing_key_without_leaking_values(
        client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_LOOKALIKE_API_KEY", "sk-ant-should-not-appear")
    response = client.get("/api/keycheck")
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
    body = client.post("/api/battlecard",
                       json={"competitor": "jda", "research": True}).get_json()
    assert body["ok"] is True
    assert "search is down" in body["research_error"]
    assert body["battlecard"]["researched"] is False


# ─── storage durability ────────────────────────────────────────────────────

def test_healthz_reports_storage_durability(client):
    """Uploads were lost because ephemeral storage looked identical to
    permanent storage. Durability must be stated, not inferred."""
    storage = client.get("/healthz").get_json()["storage"]
    assert storage["backend"] == "sqlite"
    assert storage["durable"] is False
    assert storage["configured"] is False


def test_a_configured_database_is_reported_as_durable(monkeypatch):
    import ciq.config
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    storage = ciq.config.Config.storage_info()
    assert storage["durable"] is True
    assert storage["backend"] == "postgres"
    assert storage["configured"] is True


def test_database_url_is_read_on_demand(monkeypatch):
    """Captured at import, a value set later would be missed."""
    import ciq.config
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert ciq.config.Config.database_url() == ""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    assert ciq.config.Config.database_url() == "postgresql://x/y"
    assert ciq.config.Config.store_target() == "postgresql://x/y"


def test_an_unreachable_database_never_falls_back_to_a_file(monkeypatch):
    """Silently degrading to local storage is precisely how a library
    disappears on the next deploy. It must fail loudly instead."""
    import sys
    monkeypatch.setenv("DATABASE_URL", "postgresql://ciq@127.0.0.1:1/nope")
    monkeypatch.setenv("CIQ_SECRET_KEY", "test-secret")
    for module in [m for m in list(sys.modules)
                   if m == "ciq" or m.startswith("ciq.")] + ["app"]:
        sys.modules.pop(module, None)
    import app as application
    application.app.config["TESTING"] = True
    with application.app.test_client() as c:
        response = c.get("/healthz")
        body = response.get_json()
    assert response.status_code == 500
    assert body["ok"] is False
    assert body["storage"]["configured"] is True
    assert body["storage"]["reachable"] is False
    # It must not claim to be durable while being unusable.
    assert "not reachable" in body["error"]


# ─── API routes must never answer with HTML ────────────────────────────────

def test_a_crashing_api_route_returns_json_not_an_html_page(client, monkeypatch):
    """An HTML error page reached the browser as "Unexpected token '<'", which
    hid the real fault instead of reporting it."""
    import app as application
    monkeypatch.setattr(application, "search",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("connection to server failed")))
    application.app.config["PROPAGATE_EXCEPTIONS"] = False
    response = client.get("/api/search?q=o9")
    assert response.status_code == 500
    assert response.mimetype == "application/json"
    body = response.get_json()
    assert body["ok"] is False
    assert "connection to server failed" in body["error"]
    # The hint must point at the likely cause.
    assert "DATABASE_URL" in body["error"]


def test_an_unknown_api_route_returns_json(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.mimetype == "application/json"
    assert response.get_json()["ok"] is False


def test_a_wrong_method_returns_json(client):
    response = client.delete("/api/search")
    assert response.status_code == 405
    assert response.mimetype == "application/json"
    assert response.get_json()["ok"] is False


def test_the_page_itself_is_still_html(client):
    assert client.get("/").mimetype == "text/html"


def test_diagnose_is_open_and_names_the_failing_stage(client):
    """It is needed exactly when the app cannot serve, so it must not require
    an admin session that cannot be established."""
    report = client.get("/api/diagnose").get_json()["report"]
    assert report["ok"] is False
    first = report["stages"][0]
    assert first["name"] == "Configuration"
    assert first["ok"] is False
    assert "CIQ_DB_HOST" in first["fix"]


def test_diagnose_never_reveals_the_password(client, monkeypatch):
    monkeypatch.setenv("CIQ_DB_HOST", "nope.invalid.example")
    monkeypatch.setenv("CIQ_DB_USER", "postgres.abc")
    monkeypatch.setenv("CIQ_DB_PASSWORD", "TopSecretValue123")
    monkeypatch.setenv("CIQ_DB_NAME", "postgres")
    body = client.get("/api/diagnose").get_data(as_text=True)
    assert "TopSecretValue123" not in body
    assert "postgres.abc" in body        # the user is shown, the password is not


# ─── cost control ──────────────────────────────────────────────────────────

def test_research_is_off_by_default(client, monkeypatch):
    """Research is the dominant cost, so it must be opt in per request."""
    import ciq.llm as llm
    called = {"n": 0}
    monkeypatch.setattr(llm, "research_competitor",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {})
    monkeypatch.setattr(llm, "build_battlecard",
                        lambda competitor, passages, research: {"competitor": competitor,
                                                                "scorecard": []})
    add(client, note="Blue Yonder notes.", competitor="Blue Yonder",
        title="BY", category="information")
    client.post("/api/battlecard", json={"competitor": "jda"})
    assert called["n"] == 0
    client.post("/api/battlecard", json={"competitor": "jda", "research": True,
                                         "refresh": True})
    assert called["n"] == 1


def test_a_battlecard_is_reused_rather_than_regenerated(client, monkeypatch):
    import ciq.llm as llm
    built = {"n": 0}

    def fake_build(competitor, passages, research):
        built["n"] += 1
        return {"competitor": competitor, "scorecard": []}

    monkeypatch.setattr(llm, "build_battlecard", fake_build)
    add(client, note="notes", competitor="Blue Yonder", title="BY",
        category="information")
    first = client.post("/api/battlecard", json={"competitor": "jda"}).get_json()
    second = client.post("/api/battlecard", json={"competitor": "jda"}).get_json()
    assert built["n"] == 1
    assert first["cached"] is False and second["cached"] is True
    # An explicit refresh must still rebuild.
    client.post("/api/battlecard", json={"competitor": "jda", "refresh": True})
    assert built["n"] == 2


def test_the_chat_window_is_bounded(client, monkeypatch):
    """Each turn resends the window, so an unbounded one grows cost with the
    square of the conversation length."""
    import ciq.llm as llm
    seen = {}

    def fake_chat(messages, passages, research=True):
        seen["count"] = len(messages)
        seen["research"] = research
        return {"answer": "ok", "citations": [], "web_sources": []}

    monkeypatch.setattr(llm, "chat", fake_chat)
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
               for i in range(30)]
    client.post("/api/chat", json={"messages": history})
    assert seen["count"] <= 6
    assert seen["research"] is False       # opt in, not default


def test_usage_is_recorded_and_reported(client):
    from ciq import db
    import app as application
    conn = db.connect(application.Config.store_target())
    db.record_usage(conn, {"feature": "battlecard", "model": "claude-opus-5",
                           "input_tokens": 60000, "output_tokens": 5000,
                           "web_searches": 5, "cost_usd": 0.49})
    body = client.get("/api/usage").get_json()
    assert body["totals"]["calls"] == 1
    assert round(body["totals"]["cost"], 2) == 0.49
    assert body["by_feature"][0]["feature"] == "battlecard"
    assert body["research_by_default"] is False


def test_the_daily_budget_blocks_further_calls(client, monkeypatch):
    """A limit that has to be remembered at each call site is not a limit, so
    it is enforced in one place that every feature passes through."""
    import ciq.config, ciq.llm as llm
    from ciq import db
    import app as application

    monkeypatch.setattr(ciq.config.Config, "DAILY_BUDGET_USD", 1.00)
    conn = db.connect(ciq.config.Config.store_target())

    assert application._budget_status()["ok"] is True
    llm._enforce_budget()                      # under budget, no exception

    db.record_usage(conn, {"feature": "battlecard", "cost_usd": 1.20})
    status = application._budget_status()
    assert status["ok"] is False
    assert status["remaining"] == 0
    with pytest.raises(llm.BudgetExceeded):
        llm._enforce_budget()


def test_an_exceeded_budget_is_reported_as_json_not_a_crash(client, monkeypatch):
    import ciq.config
    from ciq import db
    monkeypatch.setattr(ciq.config.Config, "DAILY_BUDGET_USD", 0.01)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    db.record_usage(db.connect(ciq.config.Config.store_target()),
                    {"feature": "chat", "cost_usd": 5.0})
    response = client.post("/api/chat", json={"messages": [
        {"role": "user", "content": "hello"}]})
    assert response.status_code == 429
    body = response.get_json()
    assert body["budget_exceeded"] is True
    assert "daily API budget" in body["error"]


def test_a_zero_budget_disables_the_guard(client, monkeypatch):
    """Some deployments want no ceiling; zero must mean off, not block all."""
    import ciq.config, ciq.llm as llm
    from ciq import db
    monkeypatch.setattr(ciq.config.Config, "DAILY_BUDGET_USD", 0)
    db.record_usage(db.connect(ciq.config.Config.store_target()),
                    {"feature": "chat", "cost_usd": 999.0})
    import app as application
    assert application._budget_status()["enforced"] is False
    llm._enforce_budget()


def test_usage_reports_the_budget(client):
    body = client.get("/api/usage").get_json()
    assert "budget" in body
    assert body["budget"]["limit"] >= 0
