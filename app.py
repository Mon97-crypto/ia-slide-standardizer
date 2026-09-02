"""Competitor Intelligence for Impact Analytics.

A shared, searchable library of competitor material with grounded AI analysis.
Everything runs in one process: Flask serves the UI and the API, SQLite holds
the library, and Claude is called from the server so the API key never reaches
a browser.
"""
from __future__ import annotations

import json
import os
import secrets
from functools import wraps

from flask import (Flask, jsonify, render_template, request, send_file,
                   session)
from werkzeug.exceptions import HTTPException

from ciq import db, ingest, llm
from ciq.competitors import canonical_name, known_names, threatened_products
from ciq.config import CATEGORIES, Config
from ciq.fetchers import FetchError, fetch
from ciq.search import gather_passages, parse_query, retrieve_passages, search

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_UPLOAD_BYTES
# Shared across workers, so an admin session stays valid on every worker.
app.secret_key = Config.secret_key()


def store():
    return db.connect(Config.store_target())


def fail(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return fail("Admin access required.", 403)
        return view(*args, **kwargs)
    return wrapper


# ─── pages ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        categories=CATEGORIES,
        competitors=known_names(),
        ai_enabled=llm.available(),
    )


@app.route("/healthz")
def healthz():
    """Render health check. Confirms the database is reachable, not just that
    the process is up."""
    storage = Config.storage_info()
    try:
        counts = db.stats(store())
    except Exception as exc:
        # A configured database that cannot be reached must never fall back to
        # local storage. Silently degrading to a file is exactly how a library
        # disappears on the next deploy.
        storage = {**storage, "reachable": False, "error": str(exc)}
        return jsonify({"ok": False, "storage": storage,
                        "error": f"The database is not reachable: {exc}"}), 500
    storage["reachable"] = True
    # key_source says where the key was found, or that it was not found at
    # all. It never reveals the key. This is the first thing to check when the
    # header shows "AI off".
    return jsonify({
        "ok": True,
        "ai_enabled": llm.available(),
        "key_source": Config.api_key_with_source()[1],
        "storage": storage,
        **counts,
    })


# ─── library ───────────────────────────────────────────────────────────────

@app.route("/api/entries", methods=["GET"])
def api_list_entries():
    entries = db.list_entries(
        store(),
        category=request.args.get("category", ""),
        competitor=request.args.get("competitor", ""),
    )
    return jsonify({"ok": True, "entries": entries, "total": len(entries)})


@app.route("/api/search")
def api_search():
    outcome = search(
        store(),
        query=request.args.get("q", ""),
        category=request.args.get("category", ""),
    )
    return jsonify({"ok": True, **outcome})


@app.route("/api/entries", methods=["POST"])
def api_create_entry():
    competitor = (request.form.get("competitor") or "").strip()
    title = (request.form.get("title") or "").strip()
    category = request.form.get("category") or "information"
    note = (request.form.get("note") or "").strip()
    file_url = (request.form.get("file_url") or "").strip()
    lovable_url = (request.form.get("lovable_url") or "").strip()
    upload = request.files.get("file")

    if not competitor:
        return fail("Add a competitor name.")
    if not title:
        return fail("Add a file title.")
    if category not in CATEGORIES:
        return fail(f"Unknown category '{category}'.")
    if not upload and not file_url and not note:
        return fail("Add a file, a link, or a note.")

    content, file_name, source_kind, status = "", "", "note", ""

    if upload and upload.filename:
        raw = upload.read()
        if len(raw) > Config.MAX_UPLOAD_BYTES:
            return fail("That file is over the upload limit.")
        try:
            content = ingest.extract_text(raw, upload.filename)
        except ingest.ExtractionError as exc:
            return fail(str(exc))
        file_name, source_kind = upload.filename, "upload"
        status = f"Extracted {len(content):,} characters from {upload.filename}."
    elif file_url:
        source_kind = "link"
        try:
            fetched = fetch(file_url)
            content = ingest.extract_text(fetched.data, fetched.filename)
            file_name = fetched.filename
            status = f"Fetched and indexed {len(content):,} characters."
        except (FetchError, ingest.ExtractionError) as exc:
            # A link that cannot be read is still worth keeping. The entry is
            # saved and stays searchable on its title and note.
            status = f"Saved without document text: {exc}"

    if not content and note:
        content, source_kind = note, source_kind or "note"

    entry = db.create_entry(store(), {
        "competitor": competitor, "title": title, "category": category,
        "note": note, "file_url": file_url, "lovable_url": lovable_url,
        "file_name": file_name, "content": content, "source_kind": source_kind,
        "extract_status": status,
    }, chunks=ingest.chunk_text(content))

    return jsonify({"ok": True, "entry": entry, "status": status}), 201


@app.route("/api/entries/<entry_id>", methods=["GET"])
def api_get_entry(entry_id: str):
    entry = db.get_entry(store(), entry_id)
    if entry is None:
        return fail("Entry not found.", 404)
    return jsonify({"ok": True, "entry": entry})


@app.route("/api/entries/<entry_id>", methods=["DELETE"])
def api_delete_entry(entry_id: str):
    if not db.delete_entry(store(), entry_id):
        return fail("Entry not found.", 404)
    return jsonify({"ok": True})


# ─── intelligence ──────────────────────────────────────────────────────────

@app.route("/api/entries/<entry_id>/analyze", methods=["POST"])
def api_analyze(entry_id: str):
    conn = store()
    entry = db.get_entry(conn, entry_id)
    if entry is None:
        return fail("Entry not found.", 404)

    # A stored analysis is reused unless the caller forces a refresh, so
    # reopening a card does not spend another API call.
    if entry.get("analysis") and not request.args.get("refresh"):
        return jsonify({"ok": True, "analysis": entry["analysis"],
                        "cached": True, "analyzed_at": entry["analyzed_at"]})

    if not entry["content"]:
        return fail("This entry has no document text to analyse.")

    try:
        analysis = llm.analyse_document(
            entry["content"], entry["competitor"], entry["title"])
    except llm.LLMUnavailable as exc:
        return fail(str(exc), 503)

    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.update_entry(conn, entry_id, {
        "analysis_json": json.dumps(analysis), "analyzed_at": stamp})
    return jsonify({"ok": True, "analysis": analysis, "cached": False,
                    "analyzed_at": stamp})


@app.route("/api/ask", methods=["POST"])
def api_ask():
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return fail("Ask a question.")

    conn = store()
    entry_id = payload.get("entry_id") or ""
    competitor = payload.get("competitor") or ""

    # An unscoped question still gets scoped when the question itself names a
    # competitor, which keeps library-wide answers on topic.
    if not entry_id and not competitor:
        competitor = parse_query(question).competitor

    passages = retrieve_passages(conn, question, entry_id=entry_id,
                                 competitor=competitor, limit=8)
    try:
        result = llm.answer_question(question, passages)
    except llm.LLMUnavailable as exc:
        return fail(str(exc), 503)
    return jsonify({"ok": True, "scope": {"entry_id": entry_id,
                                          "competitor": competitor}, **result})


@app.route("/api/battlecard", methods=["POST"])
def api_battlecard():
    payload = request.get_json(silent=True) or {}
    competitor = canonical_name((payload.get("competitor") or "").strip())
    if not competitor:
        return fail("Name a competitor.")
    # Research is on by default and can be turned off for a faster, cheaper
    # card built purely from uploaded documents.
    want_research = payload.get("research", True)

    conn = store()
    passages = gather_passages(conn, llm.BATTLECARD_THEMES, competitor)

    research, research_error = None, ""
    if want_research:
        # A short digest of what is already on file, so the researcher extends
        # and verifies the library rather than restating it.
        library_context = "\n\n".join(p["text"] for p in passages[:8])
        try:
            research = llm.research_competitor(competitor, library_context)
        except llm.LLMUnavailable as exc:
            # Research is an enhancement. Losing it must not lose the card, so
            # the failure is reported alongside a library-only result.
            research_error = str(exc)

    try:
        card = llm.build_battlecard(competitor, passages, research)
    except llm.LLMUnavailable as exc:
        return fail(str(exc), 503)

    return jsonify({
        "ok": True,
        "battlecard": card,
        "threatens": threatened_products(competitor),
        "passages_used": len(passages),
        "themes_covered": sorted({p["theme"] for p in passages}),
        "research_error": research_error,
    })


# ─── admin ─────────────────────────────────────────────────────────────────

@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    payload = request.get_json(silent=True) or {}
    supplied = payload.get("passcode") or ""
    # Constant-time compare, and the passcode never appears in page source.
    if not secrets.compare_digest(supplied, Config.ADMIN_PASSCODE):
        return fail("Wrong passcode.", 401)
    session["is_admin"] = True
    return jsonify({"ok": True})


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.pop("is_admin", None)
    return jsonify({"ok": True})


@app.route("/api/admin/export")
@admin_required
def api_admin_export():
    entries = db.list_entries(store(), limit=100000)
    buffer = json.dumps(entries, indent=2).encode()
    from io import BytesIO
    return send_file(BytesIO(buffer), mimetype="application/json",
                     as_attachment=True, download_name="ia-competitor-library.json")


@app.route("/api/admin/import", methods=["POST"])
@admin_required
def api_admin_import():
    upload = request.files.get("file")
    if not upload:
        return fail("Choose a library JSON file.")
    try:
        records = json.loads(upload.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return fail(f"That is not valid JSON: {exc}")
    if not isinstance(records, list):
        return fail("Expected a JSON array of entries.")

    conn, imported = store(), 0
    for record in records:
        if not isinstance(record, dict):
            continue
        # Accept the prototype's export shape, including base64 fileData.
        content = record.get("content") or ""
        if not content and record.get("fileData"):
            import base64
            try:
                content = base64.b64decode(record["fileData"]).decode(
                    "utf-8", errors="replace")
            except Exception:
                content = ""
        note = record.get("note") or ""
        if not content:
            content = note

        db.create_entry(conn, {
            "competitor": record.get("competitor") or "",
            "title": record.get("title") or "Untitled",
            "category": (record.get("category") if record.get("category")
                         in CATEGORIES else "information"),
            "note": note,
            "file_url": record.get("fileUrl") or record.get("file_url") or "",
            "lovable_url": record.get("lovable") or record.get("lovable_url") or "",
            "file_name": record.get("fileName") or record.get("file_name") or "",
            "content": content,
            "source_kind": "import",
            "created_at": record.get("addedAt") or record.get("created_at") or "",
        }, chunks=ingest.chunk_text(content))
        imported += 1

    return jsonify({"ok": True, "imported": imported, **db.stats(conn)})


@app.route("/api/admin/keycheck")
@admin_required
def api_admin_keycheck():
    """Explain why the Anthropic key was or was not found.

    Reports variable and file names only, never values, so it is safe to read
    against a live deployment.
    """
    return jsonify({"ok": True, "diagnostics": Config.key_diagnostics()})


@app.route("/api/admin/selftest", methods=["POST"])
@admin_required
def api_admin_selftest():
    """Confirm the Claude integration end to end, from a live deployment.

    Admin gated because it spends a small amount of API credit and reports
    configuration detail. It never returns the key itself.
    """
    return jsonify({"ok": True, "report": llm.self_test()})


@app.route("/api/admin/clear", methods=["POST"])
@admin_required
def api_admin_clear():
    return jsonify({"ok": True, "deleted": db.clear_all(store())})


@app.route("/api/stats")
def api_stats():
    return jsonify({"ok": True, "ai_enabled": llm.available(), **db.stats(store())})


@app.errorhandler(413)
def too_large(_):
    limit = Config.MAX_UPLOAD_BYTES // (1024 * 1024)
    return fail(f"That upload is over the {limit} MB limit.", 413)


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.path == "/healthz"


@app.errorhandler(HTTPException)
def handle_http_error(exc: HTTPException):
    """Answer API routes in JSON even for 404, 405 and the rest."""
    if not _wants_json():
        return exc
    return jsonify({"ok": False, "error": exc.description,
                    "status": exc.code}), exc.code


@app.errorhandler(Exception)
def handle_unexpected_error(exc: Exception):
    """Never answer an API route with an HTML error page.

    The browser parses every API response as JSON, so Flask's default HTML
    error page surfaced as "Unexpected token '<'" and hid the real fault,
    which is usually the database being unreachable.
    """
    app.logger.exception("Unhandled error on %s", request.path)
    if not _wants_json():
        raise exc
    message = f"{type(exc).__name__}: {exc}"
    storage = Config.storage_info()
    if not storage.get("durable") or "connect" in str(exc).lower():
        message += (" The database may be unreachable. Check DATABASE_URL "
                    "and the service logs.")
    return jsonify({"ok": False, "error": message}), 500


if __name__ == "__main__":
    db.connect(Config.store_target())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
