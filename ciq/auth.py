"""Google sign-in, restricted to a single email domain.

The library holds competitive material, so access is by company identity
rather than a shared passcode. A passcode in a browser is one screenshot away
from being everyone's passcode, and it says nothing about who acted.

Google is asked to restrict the account chooser to the allowed domain, but that
is a hint to the browser and nothing more. The domain is enforced here, on the
verified token, because the hint can be removed by whoever is signing in.
"""
from __future__ import annotations

import base64
import json
import secrets
from functools import wraps
from typing import Any
from urllib.parse import urlencode

from flask import jsonify, redirect, request, session, url_for

from .config import Config

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class AuthError(Exception):
    """Raised when a sign-in attempt must be refused."""


def configured() -> bool:
    return bool(Config.google_client_id() and Config.google_client_secret())


def current_user() -> dict[str, Any] | None:
    return session.get("user")


def _decode_id_token(id_token: str) -> dict[str, Any]:
    """Read the claims from an ID token.

    The token is not signature checked here, and does not need to be: it was
    just fetched over TLS directly from Google's token endpoint using the
    client secret, so it cannot have been supplied by the browser. The issuer
    and audience are still checked, because those catch a misconfigured client
    rather than a forged token.
    """
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except Exception as exc:
        raise AuthError("Could not read the sign-in token from Google.") from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise AuthError("The sign-in token came from an unexpected issuer.")
    if claims.get("aud") != Config.google_client_id():
        raise AuthError("The sign-in token was issued for a different client.")
    return claims


def authorise(claims: dict[str, Any]) -> dict[str, Any]:
    """Accept the claims only for a verified address in the allowed domain."""
    email = (claims.get("email") or "").strip().lower()
    domain = Config.ALLOWED_EMAIL_DOMAIN.lower()

    if not email:
        raise AuthError("Google returned no email address.")
    if not claims.get("email_verified", False):
        raise AuthError("That Google account has an unverified email address.")

    # Check the address itself, not only the hosted domain claim, so a personal
    # account that happens to carry an hd claim cannot slip through.
    if not email.endswith("@" + domain):
        raise AuthError(
            f"{email} is outside {domain}. This workspace is limited to "
            f"{domain} accounts.")
    if claims.get("hd") and claims["hd"].lower() != domain:
        raise AuthError(f"That account belongs to {claims['hd']}, not {domain}.")

    return {
        "email": email,
        "name": claims.get("name") or email.split("@")[0],
        "picture": claims.get("picture") or "",
    }


def login_url(redirect_uri: str) -> str:
    """Build the Google consent URL, with CSRF state held in the session."""
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    params = {
        "client_id": Config.google_client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
        # A hint that narrows the account chooser. Never trusted on its own.
        "hd": Config.ALLOWED_EMAIL_DOMAIN,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    """Trade an authorisation code for the signed-in user's claims."""
    import requests

    try:
        response = requests.post(GOOGLE_TOKEN_URL, timeout=20, data={
            "code": code,
            "client_id": Config.google_client_id(),
            "client_secret": Config.google_client_secret(),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
    except Exception as exc:
        raise AuthError(f"Could not reach Google to complete sign-in: {exc}") from exc

    if response.status_code != 200:
        detail = ""
        try:
            body = response.json()
            detail = body.get("error_description") or body.get("error") or ""
        except Exception:
            detail = response.text[:200]
        raise AuthError(f"Google rejected the sign-in ({response.status_code}). {detail}")

    id_token = response.json().get("id_token")
    if not id_token:
        raise AuthError("Google's response contained no identity token.")
    return authorise(_decode_id_token(id_token))


def login_required(view):
    """Gate a route on a signed-in account from the allowed domain.

    With sign-in unconfigured the route is left open, so a deployment mid-setup
    still works, and the page carries a banner saying access is unrestricted.
    Set CIQ_REQUIRE_AUTH to refuse instead of falling open.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user():
            return view(*args, **kwargs)
        if not configured():
            if Config.REQUIRE_AUTH:
                return jsonify({
                    "ok": False,
                    "error": "Sign-in is required but not configured. Set "
                             "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
                }), 503
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Sign in to continue.",
                            "auth_required": True}), 401
        return redirect(url_for("auth_login", next=request.path))
    return wrapper
