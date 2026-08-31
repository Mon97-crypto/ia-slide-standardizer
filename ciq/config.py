"""Runtime configuration, read once from the environment."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # Where the shared library lives. A real path means every teammate hitting
    # this server sees the same library, which localStorage could never do.
    DB_PATH = os.environ.get("CIQ_DB_PATH", str(BASE_DIR / "data" / "library.db"))

    # Anthropic. The key stays server side and is never sent to the browser.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    MODEL = os.environ.get("CIQ_MODEL", "claude-opus-5")
    MAX_UPLOAD_BYTES = int(os.environ.get("CIQ_MAX_UPLOAD_BYTES", 25 * 1024 * 1024))

    # Admin passcode. Verified on the server, never shipped in page source.
    ADMIN_PASSCODE = os.environ.get("CIQ_ADMIN_PASSCODE", "impact")
    SECRET_KEY = os.environ.get("CIQ_SECRET_KEY", "")

    # Outbound fetching of shared cloud links.
    ALLOW_REMOTE_FETCH = _bool("CIQ_ALLOW_REMOTE_FETCH", True)
    REMOTE_FETCH_TIMEOUT = float(os.environ.get("CIQ_REMOTE_FETCH_TIMEOUT", 20))
    REMOTE_FETCH_MAX_BYTES = int(os.environ.get("CIQ_REMOTE_FETCH_MAX_BYTES", 25 * 1024 * 1024))

    @classmethod
    def ai_enabled(cls) -> bool:
        return bool(cls.ANTHROPIC_API_KEY)


CATEGORIES = {
    "battlecard": "Battlecard",
    "client_list": "Client list",
    "master_sheet": "Master sheet",
    "information": "Research",
}
