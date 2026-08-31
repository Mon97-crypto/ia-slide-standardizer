"""Fetch shared cloud documents from the server.

The prototype fetched links in the browser and, when the browser blocked it,
relayed the document through public CORS proxies (corsproxy.io, allorigins.win).
That put confidential competitor material through third parties nobody vetted.
Fetching here instead keeps the content inside the deployment.

Because the URL comes from a user, every request is checked against an
allowlist of document hosts and the resolved address is rejected if it points
anywhere private. Without that, this endpoint would be an SSRF hole into the
deployment's own network.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from .config import Config

ALLOWED_HOSTS = {
    "docs.google.com",
    "drive.google.com",
    "drive.usercontent.google.com",
    "www.dropbox.com",
    "dl.dropboxusercontent.com",
    "dropbox.com",
    "sharepoint.com",
    "onedrive.live.com",
    "1drv.ms",
}

# Extension guessed from the export format so the right parser is used.
_FORMAT_EXTENSION = {"txt": ".txt", "csv": ".csv", "pdf": ".pdf", "xlsx": ".xlsx"}


class FetchError(Exception):
    """Raised when a shared link cannot be retrieved."""


@dataclass
class FetchResult:
    data: bytes
    filename: str
    final_url: str


def direct_url(url: str) -> tuple[str, str] | None:
    """Rewrite a share link into a direct download, plus a filename hint.

    Returns None when the link is not a recognised document host.
    """
    if not url:
        return None

    match = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return (f"https://docs.google.com/document/d/{match.group(1)}/export?format=txt",
                "google-doc.txt")

    match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return (f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv",
                "google-sheet.csv")

    match = re.search(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return (f"https://docs.google.com/presentation/d/{match.group(1)}/export/pdf",
                "google-slides.pdf")

    match = (re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
             or re.search(r"drive\.google\.com/.*[?&]id=([a-zA-Z0-9_-]+)", url))
    if match:
        return (f"https://drive.usercontent.google.com/download?id={match.group(1)}&export=download",
                "drive-file")

    if "dropbox.com" in url:
        cleaned = re.sub(r"[?&]dl=[01]", "", url)
        separator = "&" if "?" in cleaned else "?"
        name = urlparse(cleaned).path.rsplit("/", 1)[-1] or "dropbox-file"
        return (f"{cleaned}{separator}dl=1", name)

    return None


def _assert_public_host(hostname: str) -> None:
    """Reject anything resolving into private or loopback space."""
    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve {hostname}.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast):
            raise FetchError("That link resolves to a private address.")


def _host_allowed(hostname: str) -> bool:
    hostname = hostname.lower()
    return any(hostname == host or hostname.endswith("." + host)
               for host in ALLOWED_HOSTS)


def fetch(url: str) -> FetchResult:
    """Download a shared document. Raises FetchError with a usable message."""
    if not Config.ALLOW_REMOTE_FETCH:
        raise FetchError("Remote fetching is disabled on this deployment.")

    rewritten = direct_url(url)
    if rewritten is None:
        raise FetchError(
            "Link not recognised. Use a Google Docs, Sheets, Slides, Drive or "
            "Dropbox share link, or upload the file directly.")
    target, filename = rewritten

    parsed = urlparse(target)
    if parsed.scheme != "https":
        raise FetchError("Only https links are fetched.")
    if not _host_allowed(parsed.hostname or ""):
        raise FetchError(f"Host {parsed.hostname} is not an allowed document host.")
    _assert_public_host(parsed.hostname)

    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise FetchError("Server is missing the requests package.") from exc

    try:
        response = requests.get(
            target,
            timeout=Config.REMOTE_FETCH_TIMEOUT,
            allow_redirects=True,
            stream=True,
            headers={"User-Agent": "IA-CompetitorIntelligence/1.0"},
        )
    except Exception as exc:
        raise FetchError(f"Could not reach the file: {exc}") from exc

    if response.status_code in (401, 403):
        raise FetchError(
            'Access denied. Set sharing to "Anyone with the link" and retry.')
    if response.status_code >= 400:
        raise FetchError(f"The host returned status {response.status_code}.")

    # Redirects must not be allowed to escape the allowlist.
    final_host = urlparse(response.url).hostname or ""
    if not _host_allowed(final_host):
        raise FetchError(f"Link redirected to a disallowed host ({final_host}).")

    chunks, total = [], 0
    for block in response.iter_content(65536):
        total += len(block)
        if total > Config.REMOTE_FETCH_MAX_BYTES:
            raise FetchError("That file is larger than the fetch limit.")
        chunks.append(block)
    data = b"".join(chunks)

    if not data:
        raise FetchError("The host returned an empty file.")

    # Google serves an HTML sign-in or scan-warning page instead of the file
    # when a document is not actually shared. Detect it rather than indexing it.
    head = data[:2048].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        if any(marker in head for marker in
               (b"sign in", b"google drive", b"virus scan", b"request access")):
            raise FetchError(
                "The host returned a sign-in page rather than the file. Set "
                'sharing to "Anyone with the link", or upload the file.')

    # Give the parser a usable extension.
    content_type = (response.headers.get("content-type") or "").lower()
    if "." not in filename:
        if "pdf" in content_type:
            filename += ".pdf"
        elif "spreadsheet" in content_type or "excel" in content_type:
            filename += ".xlsx"
        elif "wordprocessing" in content_type or "msword" in content_type:
            filename += ".docx"
        elif "presentation" in content_type:
            filename += ".pptx"
        elif "csv" in content_type:
            filename += ".csv"
        else:
            filename += ".txt"

    return FetchResult(data=data, filename=filename, final_url=response.url)
