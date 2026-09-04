"""Access control tests.

The library holds competitive material, so who gets in is the security
boundary. These cover the ways a wrong account could slip through.
"""
from __future__ import annotations

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
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
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


def sign_in(client, email="analyst@impactanalytics.co"):
    with client.session_transaction() as sess:
        sess["user"] = {"email": email, "name": "Analyst", "picture": ""}


# ─── domain enforcement ────────────────────────────────────────────────────

def test_an_impactanalytics_account_is_accepted():
    from ciq.auth import authorise
    user = authorise({"email": "a.b@impactanalytics.co", "email_verified": True,
                      "name": "AB", "hd": "impactanalytics.co"})
    assert user["email"] == "a.b@impactanalytics.co"


@pytest.mark.parametrize("claims,reason", [
    ({"email": "someone@gmail.com", "email_verified": True}, "outside"),
    # A lookalike domain must not pass a naive substring check.
    ({"email": "x@impactanalytics.co.attacker.com", "email_verified": True}, "outside"),
    ({"email": "x@notimpactanalytics.co", "email_verified": True}, "outside"),
    ({"email": "x@impactanalytics.co", "email_verified": False}, "unverified"),
    # A personal account carrying someone else's hosted domain claim.
    ({"email": "x@impactanalytics.co", "email_verified": True,
      "hd": "other.com"}, "belongs to"),
    ({"email": "", "email_verified": True}, "no email"),
])
def test_other_accounts_are_refused(claims, reason):
    from ciq.auth import AuthError, authorise
    with pytest.raises(AuthError, match=reason):
        authorise(claims)


def test_the_domain_is_configurable(monkeypatch):
    import ciq.config
    from ciq.auth import AuthError, authorise
    monkeypatch.setattr(ciq.config.Config, "ALLOWED_EMAIL_DOMAIN", "example.com")
    assert authorise({"email": "a@example.com", "email_verified": True})
    with pytest.raises(AuthError):
        authorise({"email": "a@impactanalytics.co", "email_verified": True})


# ─── token handling ────────────────────────────────────────────────────────

def _token(claims):
    import base64, json
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{body}.signature"


def test_a_token_for_another_client_is_refused(monkeypatch):
    from ciq.auth import AuthError, _decode_id_token
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "our-client")
    with pytest.raises(AuthError, match="different client"):
        _decode_id_token(_token({"iss": "accounts.google.com",
                                 "aud": "someone-elses-client"}))


def test_a_token_from_another_issuer_is_refused(monkeypatch):
    from ciq.auth import AuthError, _decode_id_token
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "our-client")
    with pytest.raises(AuthError, match="unexpected issuer"):
        _decode_id_token(_token({"iss": "evil.example.com", "aud": "our-client"}))


# ─── route gating ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/api/search?q=o9", "/api/entries", "/api/library/export",
])
def test_data_routes_refuse_an_anonymous_caller(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.get_json()["auth_required"] is True


@pytest.mark.parametrize("path,method", [
    ("/api/chat", "post"), ("/api/deck", "post"),
    ("/api/battlecard", "post"), ("/api/library/clear", "post"),
])
def test_write_routes_refuse_an_anonymous_caller(client, path, method):
    assert getattr(client, method)(path, json={}).status_code == 401


def test_the_page_redirects_an_anonymous_visitor_to_sign_in(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_a_signed_in_user_reaches_the_page_and_the_data(client):
    sign_in(client)
    assert client.get("/").status_code == 200
    assert client.get("/api/search?q=o9").status_code == 200
    assert client.get("/api/library/export").status_code == 200


def test_signing_out_revokes_access(client):
    sign_in(client)
    assert client.get("/api/search?q=o9").status_code == 200
    client.post("/auth/logout")
    assert client.get("/api/search?q=o9").status_code == 401


def test_health_and_diagnose_stay_open(client):
    """Both are needed before anyone can sign in."""
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/diagnose").status_code == 200


def test_the_callback_rejects_a_mismatched_state(client):
    """Without this check a third party could complete a sign-in for someone."""
    response = client.get("/auth/callback?code=abc&state=forged")
    assert response.status_code == 400
    assert b"expired" in response.data


def test_no_passcode_remains_anywhere():
    """The shared passcode is gone, not merely hidden."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ("app.py", "templates/index.html", "ciq/config.py"):
        text = (root / name).read_text().lower()
        assert "adminpass" not in text
        assert "admin_passcode" not in text
