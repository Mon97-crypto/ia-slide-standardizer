"""Take the whole library out, files included, and put it back.

The library used to export as JSON: entry rows, and nothing else. Once the
uploads themselves were kept that export became quietly lossy - it is the
obvious thing to reach for as a backup, and every document would have been
missing from it.

A backup is what makes "forever" something the team holds rather than
something they hope the database keeps, so it is a zip: the entries as JSON,
and every stored document as a real file beside them.

The archive is built on disk rather than in memory. A library of decks is
larger than a small container's RAM, and a backup that kills the process is
worse than no backup.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Any, Callable

MANIFEST = "library.json"
FILE_DIR = "files"
# A zip entry's name, not a path to follow. Anything that could climb out of
# the extraction directory is rewritten before it is ever used.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _member_name(entry_id: str, file_name: str) -> str:
    stem = _UNSAFE.sub("-", os.path.basename(file_name or "")).strip("-.")
    return f"{FILE_DIR}/{entry_id}__{stem or 'document'}"[:180]


def build(entries: list[dict[str, Any]],
          load_file: Callable[[str], dict[str, Any] | None]) -> tuple[str, str]:
    """Write the archive to a temporary file. Returns (path, download name).

    `load_file` is called once per entry rather than every document being held
    in memory at once, so the peak cost is one document, not the library.
    """
    handle, path = tempfile.mkstemp(suffix=".zip", prefix="ia-library-")
    os.close(handle)
    manifest = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for entry in entries:
            record = dict(entry)
            record.pop("has_file", None)
            held = load_file(entry["id"])
            if held is not None:
                member = _member_name(entry["id"], held["file_name"])
                archive.writestr(member, held["data"])
                record["file"] = {
                    "path": member,
                    "name": held["file_name"],
                    "mime_type": held["mime_type"],
                    "bytes": held["byte_size"],
                }
            manifest.append(record)
        archive.writestr(MANIFEST, json.dumps(
            {"exported_at": datetime.now(timezone.utc).isoformat(),
             "entries": manifest}, indent=2, default=str))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return path, f"ia-competitor-library-{stamp}.zip"


class Archive:
    """A backup being read back in."""

    def __init__(self, zip_file: zipfile.ZipFile, records: list[dict]):
        self.zip = zip_file
        self.records = records

    def file_for(self, record: dict) -> tuple[str, str, bytes] | None:
        """The document belonging to one record, if the archive carries it."""
        spec = record.get("file")
        if not isinstance(spec, dict):
            return None
        member = spec.get("path") or ""
        # Only ever read a name the archive actually lists. Trusting the path
        # in the manifest is how a crafted backup reads outside the archive.
        if member not in self.zip.namelist():
            return None
        try:
            data = self.zip.read(member)
        except Exception:
            return None
        if not data:
            return None
        return (spec.get("name") or os.path.basename(member),
                spec.get("mime_type") or "", data)


def read(data: bytes) -> Archive:
    """Open a backup. Raises ValueError with something worth showing."""
    import io

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"That is not a readable zip: {exc}") from exc
    if MANIFEST not in archive.namelist():
        raise ValueError(
            f"That zip has no {MANIFEST} in it, so it is not a library backup.")
    try:
        payload = json.loads(archive.read(MANIFEST).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"The backup's {MANIFEST} is not valid JSON: {exc}")
    records = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"The backup's {MANIFEST} holds no list of entries.")
    return Archive(archive, [r for r in records if isinstance(r, dict)])
