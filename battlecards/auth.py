"""Optional HTTP basic auth for the whole app.

Battlecards hold competitive intelligence, customer names and unpublished
numbers. A public URL is the wrong place for that, so this module gates every
route behind credentials supplied by the environment.

Set IA_AUTH_USER and IA_AUTH_PASSWORD to turn it on. No credential is ever
stored in the repository. When the variables are unset the app runs open and
logs a warning, which keeps local development frictionless.
"""

from __future__ import annotations

import hmac
import logging
import os

from flask import Response, request

log = logging.getLogger(__name__)

REALM = 'Impact Analytics internal tools'
# Static files and the health check stay open so Render's probe keeps passing.
OPEN_PATHS = ('/static/', '/healthz')


def credentials():
    """Return the configured user and password, or None when auth is off."""
    user = os.environ.get('IA_AUTH_USER', '').strip()
    password = os.environ.get('IA_AUTH_PASSWORD', '')
    if not user or not password:
        return None
    return user, password


def _matches(supplied: str, expected: str) -> bool:
    """Compare in constant time, so a wrong guess leaks no timing signal."""
    return hmac.compare_digest(supplied.encode('utf-8'), expected.encode('utf-8'))


def install(app):
    """Attach the auth check to a Flask app."""
    configured = credentials()
    if not configured:
        log.warning('IA_AUTH_USER and IA_AUTH_PASSWORD are unset. Every route is '
                    'open. Set both before you deploy anything with real content.')

    @app.before_request
    def require_auth():
        expected = credentials()
        if not expected:
            return None
        path = request.path or '/'
        if path.startswith(OPEN_PATHS):
            return None
        auth = request.authorization
        if auth and auth.username and auth.password is not None:
            user_ok = _matches(auth.username, expected[0])
            password_ok = _matches(auth.password, expected[1])
            if user_ok and password_ok:
                return None
        return Response(
            'Authentication required.', 401,
            {'WWW-Authenticate': 'Basic realm="%s", charset="UTF-8"' % REALM})

    return app


def is_enabled() -> bool:
    return credentials() is not None
