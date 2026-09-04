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
    # Where the shared library lives. A real server-side store means every
    # teammate sees the same library, which localStorage could never do.
    #
    # DATABASE_URL wins when set: a managed Postgres survives deploys and
    # restarts, which a container-local SQLite file does not.
    DB_PATH = os.environ.get("CIQ_DB_PATH", str(BASE_DIR / "data" / "library.db"))

    @classmethod
    def database_url(cls) -> str:
        """Build the connection target, on demand.

        DATABASE_URL wins when set. Surrounding quotes and whitespace are
        stripped, because a value pasted with either is a configuration slip
        rather than an intent.

        Otherwise the connection is assembled from separate parts. Hand
        assembling a URL is where this goes wrong: a password containing a
        reserved character silently truncates the string, and the resulting
        failure names neither the character nor the field. Supplied as its own
        variable, a password needs no encoding and can contain anything.
        """
        url = os.environ.get("DATABASE_URL", "").strip().strip('"\'')
        if url:
            return url

        host = os.environ.get("CIQ_DB_HOST", "").strip().strip('"\'')
        if not host:
            return ""

        from urllib.parse import quote
        user = os.environ.get("CIQ_DB_USER", "postgres").strip().strip('"\'')
        password = os.environ.get("CIQ_DB_PASSWORD", "").strip('"\'')
        port = os.environ.get("CIQ_DB_PORT", "5432").strip() or "5432"
        name = os.environ.get("CIQ_DB_NAME", "postgres").strip() or "postgres"
        # safe="" so every reserved character is encoded, which is the whole
        # point of accepting the parts separately.
        return (f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
                f"@{host}:{port}/{name}")

    @classmethod
    def store_target(cls) -> str:
        return cls.database_url() or cls.DB_PATH

    @classmethod
    def storage_info(cls) -> dict:
        """Describe where the library lives and whether it will survive.

        A container filesystem is erased on every deploy. Without this being
        stated plainly, an ephemeral deployment looks identical to a permanent
        one right up until the moment the data is gone.
        """
        url = cls.database_url()
        if url:
            return {
                "backend": "postgres",
                "durable": True,
                "configured": True,
            }
        return {
            "backend": "sqlite",
            # A local file is durable on a developer machine and ephemeral on a
            # container host. Treated as not durable, because assuming the safe
            # case is how uploads get lost.
            "durable": False,
            "configured": False,
            "path": cls.DB_PATH,
        }

    # Anthropic. The key stays server side and is never sent to the browser.
    # Read lazily rather than captured at import, so a key added to the
    # environment takes effect without depending on when this module loaded.
    #
    # Render offers two separate features with similar names: Environment
    # Variables, which land in os.environ, and Secret Files, which are mounted
    # under /etc/secrets and never appear in the environment at all. A key put
    # in the wrong one would otherwise look simply absent, so both are checked.
    SECRET_FILE_DIR = os.environ.get("CIQ_SECRET_FILE_DIR", "/etc/secrets")
    MODEL = os.environ.get("CIQ_MODEL", "claude-opus-5")
    MAX_UPLOAD_BYTES = int(os.environ.get("CIQ_MAX_UPLOAD_BYTES", 25 * 1024 * 1024))

    # Access is by company identity through Google, not a shared passcode.
    ALLOWED_EMAIL_DOMAIN = os.environ.get(
        "CIQ_ALLOWED_EMAIL_DOMAIN", "impactanalytics.co").strip().lstrip("@").lower()
    REQUIRE_AUTH = _bool("CIQ_REQUIRE_AUTH", False)

    @classmethod
    def google_client_id(cls) -> str:
        return os.environ.get("GOOGLE_CLIENT_ID", "").strip().strip('"\'')

    @classmethod
    def google_client_secret(cls) -> str:
        return os.environ.get("GOOGLE_CLIENT_SECRET", "").strip().strip('"\'')
    SECRET_KEY = os.environ.get("CIQ_SECRET_KEY", "")

    # Outbound fetching of shared cloud links.
    ALLOW_REMOTE_FETCH = _bool("CIQ_ALLOW_REMOTE_FETCH", True)
    REMOTE_FETCH_TIMEOUT = float(os.environ.get("CIQ_REMOTE_FETCH_TIMEOUT", 20))
    REMOTE_FETCH_MAX_BYTES = int(os.environ.get("CIQ_REMOTE_FETCH_MAX_BYTES", 25 * 1024 * 1024))

    @classmethod
    def api_key_with_source(cls) -> tuple[str, str]:
        """Return the Anthropic key and where it came from."""
        from_env = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if from_env:
            return from_env, "environment"
        try:
            path = Path(cls.SECRET_FILE_DIR) / "ANTHROPIC_API_KEY"
            if path.is_file():
                value = path.read_text().strip()
                if value:
                    return value, "secret_file"
        except OSError:
            pass
        return "", "missing"

    @classmethod
    def api_key(cls) -> str:
        return cls.api_key_with_source()[0]

    @classmethod
    def ai_enabled(cls) -> bool:
        return bool(cls.api_key())

    @classmethod
    def key_diagnostics(cls) -> dict:
        """Explain why the key was or was not found, without revealing it.

        Only names are reported, never values, so this is safe to read while
        debugging a live deployment.
        """
        _, source = cls.api_key_with_source()
        # Narrow enough to be readable, wide enough to catch a typo such as
        # ANTHROPIC_KEY or ANTROPIC_API_KEY. ANTHROPIC_BASE_URL is included on
        # purpose: an unexpected base URL redirects calls away from the real
        # API and is worth seeing here.
        related = sorted(
            name for name in os.environ
            if "ANTHROPIC" in name.upper() or "API_KEY" in name.upper()
        )[:20]
        secret_files: list[str] = []
        secret_dir_exists = False
        try:
            directory = Path(cls.SECRET_FILE_DIR)
            secret_dir_exists = directory.is_dir()
            if secret_dir_exists:
                secret_files = sorted(f.name for f in directory.iterdir())
        except OSError:
            pass
        return {
            "source": source,
            "expected_variable": "ANTHROPIC_API_KEY",
            "related_variable_names_present": related,
            "secret_file_dir": cls.SECRET_FILE_DIR,
            "secret_file_dir_exists": secret_dir_exists,
            "secret_file_names_present": secret_files,
        }

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
