"""Serving documents back out of the library.

The library stores what a user uploaded so it can be opened again. Handing a
file back is where an upload turns into a risk: the browser trusts whatever
this origin tells it a file is, and this origin also holds the session cookie.
An HTML or SVG document opened inline would run as the signed-in user.

So the content type is derived from the filename here and never taken from the
client, only a short list of formats is allowed to open in the browser at all,
and everything else is sent as a download.
"""
from __future__ import annotations

import os
import re

# Derived from the extension, never from the upload's own Content-Type header,
# which a browser will happily believe.
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".md": "text/plain",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# Safe to hand the browser to display in place. Everything absent from this set
# is downloaded instead, whatever it is. HTML and SVG are absent deliberately:
# both can carry script, and inline on this origin that script would run with
# the signed-in user's session.
INLINE_TYPES = {
    "application/pdf", "text/plain", "text/csv",
    "text/tab-separated-values", "image/png", "image/jpeg", "image/gif",
    "image/webp",
}

FALLBACK_MIME = "application/octet-stream"


def mime_for(file_name: str) -> str:
    _, extension = os.path.splitext((file_name or "").lower())
    return MIME_TYPES.get(extension, FALLBACK_MIME)


def opens_in_browser(mime_type: str) -> bool:
    return (mime_type or "").split(";")[0].strip().lower() in INLINE_TYPES


def safe_name(file_name: str, fallback: str = "document") -> str:
    """A filename safe to put in a header and in a downloads folder.

    Path separators, quotes and control characters are the parts that matter:
    they let a name break out of the header or out of the directory.
    """
    name = os.path.basename((file_name or "").strip().replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f\"']", "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or fallback


def disposition(file_name: str, mime_type: str) -> tuple[bool, str]:
    """How to serve this file: (as_attachment, download_name)."""
    return not opens_in_browser(mime_type), safe_name(file_name)
