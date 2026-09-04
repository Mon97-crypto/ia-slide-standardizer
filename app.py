"""Competitor Intelligence for Impact Analytics.

A shared, searchable library of competitor material with grounded AI analysis.
Everything runs in one process: Flask serves the UI and the API, SQLite holds
the library, and Claude is called from the server so the API key never reaches
a browser.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import uuid
from functools import wraps

from flask import (Flask, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from werkzeug.exceptions import HTTPException

from ciq import auth, db, deck as deckgen, diagnose as diag, ingest, llm
from ciq.competitors import canonical_name, known_names, threatened_products
from ciq.config import CATEGORIES, Config
from ciq.auth import current_user, login_required
from ciq.fetchers import FetchError, fetch
from ciq.search import gather_passages, parse_query, retrieve_passages, search

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_UPLOAD_BYTES
# Shared across workers, so an admin session stays valid on every worker.
app.secret_key = Config.secret_key()

# Generated decks, held briefly so the browser can fetch the file it was
# just offered. Small and short lived by design.
DECK_CACHE: dict[str, tuple] = {}
BATTLECARD_CACHE: dict[str, dict] = {}


def store():
    return db.connect(Config.store_target())


def _record_usage(row: dict) -> None:
    """Attribute each API call to the person who triggered it."""
    user = current_user() or {}
    db.record_usage(store(), {**row, "user_email": user.get("email", "")})


def _budget_status() -> dict:
    """How much of today's budget is left."""
    limit = Config.DAILY_BUDGET_USD
    if limit <= 0:
        return {"ok": True, "limit": 0, "spent": 0, "remaining": 0, "enforced": False}
    try:
        spent = db.spend_today(store())
    except Exception:
        # A metering failure must not block the product.
        return {"ok": True, "limit": limit, "spent": 0, "remaining": limit,
                "enforced": True}
    return {"ok": spent < limit, "limit": limit, "spent": round(spent, 4),
            "remaining": round(max(0.0, limit - spent), 4), "enforced": True}


llm.set_usage_sink(_record_usage)
llm.set_budget_check(_budget_status)


def fail(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _redirect_uri() -> str:
    """Google requires an exact, absolute redirect URI."""
    return url_for("auth_callback", _external=True, _scheme=(
        "https" if not request.host.startswith("127.0.0.1")
        and not request.host.startswith("localhost") else "http"))


# ─── pages ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template(
        "index.html",
        categories=CATEGORIES,
        competitors=known_names(),
        ai_enabled=llm.available(),
        user=current_user(),
        auth_configured=auth.configured(),
        domain=Config.ALLOWED_EMAIL_DOMAIN,
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
        # Name the host that was actually parsed. A DNS failure reports only
        # "Name or service not known" and never says what it tried, so a
        # mangled connection string is indistinguishable from a real outage.
        detail = db.describe_target(Config.database_url())
        resolves, dns = db.resolve_host(detail.get("host") or "")
        storage = {**storage, "reachable": False, "error": str(exc),
                   "host": detail.get("host"), "port": detail.get("port"),
                   "user": detail.get("user"), "database": detail.get("database"),
                   "host_resolves": resolves, "dns": dns,
                   "issues": detail.get("issues", [])}
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
@login_required
def api_list_entries():
    entries = db.list_entries(
        store(),
        category=request.args.get("category", ""),
        competitor=request.args.get("competitor", ""),
    )
    return jsonify({"ok": True, "entries": entries, "total": len(entries)})


@app.route("/api/search")
@login_required
def api_search():
    outcome = search(
        store(),
        query=request.args.get("q", ""),
        category=request.args.get("category", ""),
    )
    return jsonify({"ok": True, **outcome})


@app.route("/api/entries", methods=["POST"])
@login_required
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
@login_required
def api_get_entry(entry_id: str):
    entry = db.get_entry(store(), entry_id)
    if entry is None:
        return fail("Entry not found.", 404)
    return jsonify({"ok": True, "entry": entry})


@app.route("/api/entries/<entry_id>", methods=["DELETE"])
@login_required
def api_delete_entry(entry_id: str):
    if not db.delete_entry(store(), entry_id):
        return fail("Entry not found.", 404)
    return jsonify({"ok": True})


# ─── intelligence ──────────────────────────────────────────────────────────

@app.route("/api/entries/<entry_id>/analyze", methods=["POST"])
@login_required
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
@login_required
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


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    """Conversational intelligence over the library, with optional research."""
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages") or []
    if not messages or not (messages[-1].get("content") or "").strip():
        return fail("Ask a question.")
    # Keep the window bounded so a long thread cannot grow without limit.
    # Every turn resends the whole window, so cost grows with the square of
    # the conversation length. Six turns keeps context without that.
    messages = [{"role": m["role"], "content": m["content"]}
                for m in messages[-6:]
                if m.get("role") in ("user", "assistant") and m.get("content")]

    conn = store()
    question = messages[-1]["content"]
    competitor = payload.get("competitor") or parse_query(question).competitor
    passages = retrieve_passages(conn, question, competitor=competitor, limit=6)
    if not passages:
        # Nothing competitor specific, so fall back to the whole library.
        passages = retrieve_passages(conn, question, limit=6)

    try:
        result = llm.chat(messages, passages,
                          research=bool(payload.get("research", Config.RESEARCH_BY_DEFAULT)))
    except llm.LLMUnavailable as exc:
        return fail(str(exc), 503)
    return jsonify({"ok": True, "competitor": competitor,
                    "library_passages": len(passages), **result})


@app.route("/api/deck", methods=["POST"])
@login_required
def api_deck():
    """Draft a sales deck from a brief, the library and public research."""
    payload = request.get_json(silent=True) or {}
    brief = (payload.get("brief") or "").strip()
    if not brief:
        return fail("Describe the deck you need.")

    conn = store()
    competitor = payload.get("competitor") or parse_query(brief).competitor
    passages = (gather_passages(conn, llm.BATTLECARD_THEMES, competitor)
                if competitor else retrieve_passages(conn, brief, limit=16))

    research = None
    research_error = ""
    if payload.get("research", Config.RESEARCH_BY_DEFAULT) and competitor:
        try:
            research = llm.research_competitor(
                competitor, "\n\n".join(p["text"] for p in passages[:6]))
        except llm.LLMUnavailable as exc:
            research_error = str(exc)

    try:
        spec = llm.draft_deck(brief, passages, research)
    except llm.LLMUnavailable as exc:
        return fail(str(exc), 503)

    token = uuid.uuid4().hex[:12]
    DECK_CACHE[token] = (spec, deckgen.build(spec).getvalue())
    # Keep only the most recent handful, since these live in memory.
    for stale in list(DECK_CACHE)[:-8]:
        DECK_CACHE.pop(stale, None)

    return jsonify({
        "ok": True, "spec": spec, "download": f"/api/deck/{token}.pptx",
        "competitor": competitor, "library_passages": len(passages),
        "research_error": research_error,
        "research_sources": (research or {}).get("sources", []),
    })


@app.route("/api/deck/<token>.pptx")
@login_required
def api_deck_download(token: str):
    entry = DECK_CACHE.get(token)
    if entry is None:
        return fail("That deck has expired. Generate it again.", 404)
    spec, data = entry
    name = re.sub(r"[^A-Za-z0-9]+", "-", spec.get("title", "deck")).strip("-")[:60]
    from io import BytesIO
    return send_file(
        BytesIO(data), as_attachment=True, download_name=f"{name or 'deck'}.pptx",
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@app.route("/api/battlecard", methods=["POST"])
@login_required
def api_battlecard():
    payload = request.get_json(silent=True) or {}
    competitor = canonical_name((payload.get("competitor") or "").strip())
    if not competitor:
        return fail("Name a competitor.")
    # Research is on by default and can be turned off for a faster, cheaper
    # card built purely from uploaded documents.
    want_research = payload.get("research", Config.RESEARCH_BY_DEFAULT)

    conn = store()
    cache_key = f"{competitor.lower()}|{bool(want_research)}"
    if not payload.get("refresh") and cache_key in BATTLECARD_CACHE:
        cached = BATTLECARD_CACHE[cache_key]
        return jsonify({**cached, "cached": True})

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

    result = {
        "ok": True,
        "battlecard": card,
        "threatens": threatened_products(competitor),
        "passages_used": len(passages),
        "themes_covered": sorted({p["theme"] for p in passages}),
        "research_error": research_error,
    }
    # A battlecard is expensive and rarely changes between two people asking
    # for it in the same session, so it is reused unless a refresh is asked for.
    BATTLECARD_CACHE[cache_key] = result
    for stale in list(BATTLECARD_CACHE)[:-12]:
        BATTLECARD_CACHE.pop(stale, None)
    return jsonify({**result, "cached": False})


# ─── admin ─────────────────────────────────────────────────────────────────

@app.route("/auth/login")
def auth_login():
    if not auth.configured():
        return render_template("signin.html", error=(
            "Sign-in is not configured on this server. Set GOOGLE_CLIENT_ID "
            "and GOOGLE_CLIENT_SECRET."), domain=Config.ALLOWED_EMAIL_DOMAIN,
            configured=False)
    session["post_login"] = request.args.get("next", "/")
    return redirect(auth.login_url(_redirect_uri()))


@app.route("/auth/callback")
def auth_callback():
    # The state is what stops a third party from completing a sign-in on
    # someone else's behalf, so it is checked before the code is spent.
    if not request.args.get("state") or \
            request.args.get("state") != session.pop("oauth_state", None):
        return render_template("signin.html",
                               error="The sign-in attempt expired. Try again.",
                               domain=Config.ALLOWED_EMAIL_DOMAIN, configured=True), 400
    if request.args.get("error"):
        return render_template("signin.html",
                               error=f"Google reported: {request.args['error']}",
                               domain=Config.ALLOWED_EMAIL_DOMAIN, configured=True), 400
    code = request.args.get("code")
    if not code:
        return render_template("signin.html", error="Google returned no code.",
                               domain=Config.ALLOWED_EMAIL_DOMAIN, configured=True), 400
    try:
        user = auth.exchange_code(code, _redirect_uri())
    except auth.AuthError as exc:
        return render_template("signin.html", error=str(exc),
                               domain=Config.ALLOWED_EMAIL_DOMAIN, configured=True), 403

    session["user"] = user
    session.permanent = True
    return redirect(session.pop("post_login", "/") or "/")


@app.route("/auth/logout", methods=["GET", "POST"])
def auth_logout():
    session.pop("user", None)
    if request.method == "POST":
        return jsonify({"ok": True})
    return redirect("/")


@app.route("/api/me")
def api_me():
    return jsonify({"ok": True, "user": current_user(),
                    "auth_configured": auth.configured(),
                    "domain": Config.ALLOWED_EMAIL_DOMAIN})


@app.route("/api/library/export")
@login_required
def api_library_export():
    entries = db.list_entries(store(), limit=100000)
    buffer = json.dumps(entries, indent=2).encode()
    from io import BytesIO
    return send_file(BytesIO(buffer), mimetype="application/json",
                     as_attachment=True, download_name="ia-competitor-library.json")


@app.route("/api/library/import", methods=["POST"])
@login_required
def api_library_import():
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


@app.route("/api/diagnose")
def api_diagnose():
    """Walk the database connection stage by stage and name what failed.

    Deliberately open, because it is needed exactly when the app cannot serve
    and an admin session cannot be established. It reports host, port, user and
    database, and never the password.
    """
    return jsonify({"ok": True, "report": diag.diagnose()})


@app.route("/api/usage")
@login_required
def api_usage():
    """What the Anthropic key has actually been spent on."""
    return jsonify({"ok": True, "model": Config.MODEL,
                    "effort": Config.EFFORT,
                    "research_by_default": Config.RESEARCH_BY_DEFAULT,
                    "budget": _budget_status(),
                    **db.usage_summary(store())})


@app.route("/api/keycheck")
@login_required
def api_keycheck():
    """Explain why the Anthropic key was or was not found.

    Reports variable and file names only, never values, so it is safe to read
    against a live deployment.
    """
    return jsonify({"ok": True, "diagnostics": Config.key_diagnostics()})


@app.route("/api/selftest", methods=["POST"])
@login_required
def api_selftest():
    """Confirm the Claude integration end to end, from a live deployment.

    Admin gated because it spends a small amount of API credit and reports
    configuration detail. It never returns the key itself.
    """
    return jsonify({"ok": True, "report": llm.self_test()})


@app.route("/api/library/clear", methods=["POST"])
@login_required
def api_library_clear():
    return jsonify({"ok": True, "deleted": db.clear_all(store())})


@app.route("/api/stats")
@login_required
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


@app.errorhandler(llm.BudgetExceeded)
def handle_budget_exceeded(exc: llm.BudgetExceeded):
    return jsonify({"ok": False, "error": str(exc), "budget_exceeded": True}), 429


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
