"""Runtime configuration, read once from the environment."""
import os
import secrets
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

    @classmethod
    def secret_key(cls) -> bytes:
        """A signing key every worker agrees on.

        Generating one per process silently breaks admin sessions as soon as
        the server runs more than one worker, because a cookie signed by one
        worker fails to verify in the next. Prefer the configured value, then
        a key persisted beside the database, and only then a fresh one.
        """
        if cls.SECRET_KEY:
            return cls.SECRET_KEY.encode()

        key_path = Path(cls.DB_PATH).with_name(".secret_key")
        try:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            if key_path.exists():
                stored = key_path.read_bytes().strip()
                if stored:
                    return stored
            generated = secrets.token_hex(32).encode()
            # Exclusive create so two workers starting together cannot each
            # write a different key.
            try:
                with open(key_path, "xb") as handle:
                    handle.write(generated)
                os.chmod(key_path, 0o600)
                return generated
            except FileExistsError:
                return key_path.read_bytes().strip() or generated
        except OSError:
            # Read-only disk. Sessions will not survive a restart, which is
            # acceptable; losing the service is not.
            return secrets.token_hex(32).encode()


CATEGORIES = {
    "battlecard": "Battlecard",
    "client_list": "Client list",
    "master_sheet": "Master sheet",
    "information": "Research",
}
