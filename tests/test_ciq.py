"""Tests for the parts most likely to regress: query understanding, ranking,
ingestion and the API contract."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ciq import db, ingest  # noqa: E402
from ciq.competitors import canonical_name, resolve, threatened_products  # noqa: E402
from ciq.fetchers import direct_url  # noqa: E402
from ciq.search import parse_query, retrieve_passages, search  # noqa: E402


@pytest.fixture()
def conn():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    os.unlink(path)
    connection = db.connect(path)
    yield connection
    connection.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except OSError:
            pass


@pytest.fixture()
def seeded(conn):
    db.create_entry(conn, {
        "competitor": "o9 Solutions", "title": "o9 Battlecard Q2 2026",
        "category": "battlecard",
        "note": "Enterprise planning platform. Strong in CPG and automotive.",
        "content": "o9 is an enterprise planning platform with a knowledge graph. "
                   "Higher price point and longer deployments than retail native tools.",
    }, chunks=["o9 has a higher price point and longer deployments."])
    db.create_entry(conn, {
        "competitor": "Blue Yonder", "title": "Blue Yonder Overview",
        "category": "information", "note": "Mature end to end suite.",
        "content": "Blue Yonder, formerly JDA Software. Weaknesses include legacy "
                   "architecture and long implementation timelines.",
    }, chunks=["Weaknesses include legacy architecture and long implementation timelines."])
    db.create_entry(conn, {
        "competitor": "Relex Solutions", "title": "Relex Client References",
        "category": "client_list", "note": "Grocery heavy client base.",
        "content": "Relex client references are concentrated in grocery retail.",
    }, chunks=["Relex client references are concentrated in grocery retail."])
    return conn


# ─── competitor resolution ─────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("o9", "o9 Solutions"),
    ("O9 SOLUTIONS", "o9 Solutions"),
    ("BY", "Blue Yonder"),
    ("jda", "Blue Yonder"),          # legacy name maps to the current company
    ("JDA Software", "Blue Yonder"),
    ("relex", "Relex Solutions"),
])
def test_alias_resolution(raw, expected):
    assert canonical_name(raw) == expected


@pytest.mark.parametrize("typo,expected", [
    ("bleu yonder", "Blue Yonder"),
    ("relexx", "Relex Solutions"),
])
def test_fuzzy_resolution(typo, expected):
    name, score = resolve(typo)
    assert name == expected
    assert 0 < score <= 1.0


def test_unknown_competitor_is_not_guessed():
    name, _ = resolve("Some Brand New Vendor")
    assert name == ""


def test_unknown_competitor_is_preserved_verbatim():
    assert canonical_name("Some Brand New Vendor") == "Some Brand New Vendor"


def test_product_mapping():
    assert "PriceSmart" in threatened_products("Blue Yonder")


# ─── query understanding ───────────────────────────────────────────────────

def test_parses_competitor_and_category():
    intent = parse_query("o9 battlecard")
    assert intent.competitor == "o9 Solutions"
    assert intent.category == "battlecard"
    assert intent.terms == []


def test_parses_legacy_name_with_residual_terms():
    intent = parse_query("jda pricing notes")
    assert intent.competitor == "Blue Yonder"
    assert intent.category == "information"
    assert intent.terms == ["pricing"]


def test_multiword_category_beats_single_word():
    assert parse_query("relex client list").category == "client_list"


def test_stopwords_are_dropped():
    assert "for" not in parse_query("client list for relex").terms


# ─── ranking ───────────────────────────────────────────────────────────────

def test_the_query_the_hero_promises(seeded):
    """'o9 battlecard' must return the o9 battlecard. The prototype's
    substring match returned nothing for this exact query."""
    outcome = search(seeded, "o9 battlecard")
    assert outcome["total"] == 1
    assert outcome["results"][0]["title"] == "o9 Battlecard Q2 2026"


def test_alias_search_finds_entry_stored_under_canonical_name(seeded):
    outcome = search(seeded, "jda")
    assert [r["title"] for r in outcome["results"]] == ["Blue Yonder Overview"]


def test_typo_still_finds_the_entry(seeded):
    outcome = search(seeded, "bleu yondr")
    assert outcome["results"][0]["title"] == "Blue Yonder Overview"


def test_search_reaches_into_document_body(seeded):
    outcome = search(seeded, "legacy architecture")
    assert outcome["results"][0]["title"] == "Blue Yonder Overview"


def test_explanations_name_only_terms_that_matched(seeded):
    outcome = search(seeded, "grocery unrelatedword")
    why = " ".join(outcome["results"][0]["why"])
    assert "grocery" in why
    assert "unrelatedword" not in why


def test_category_filter_is_respected(seeded):
    outcome = search(seeded, "", category="client_list")
    assert {r["category"] for r in outcome["results"]} == {"client_list"}


def test_explicit_filter_overrides_inferred_category(seeded):
    outcome = search(seeded, "o9 battlecard", category="client_list")
    assert outcome["effective_category"] == "client_list"
    assert outcome["total"] == 0


def test_empty_query_lists_everything_newest_first(seeded):
    assert search(seeded, "")["total"] == 3


# ─── retrieval ─────────────────────────────────────────────────────────────

def test_retrieval_scopes_to_a_competitor(seeded):
    passages = retrieve_passages(
        seeded, "what are the weaknesses", competitor="Blue Yonder")
    assert passages
    assert all(p["competitor"] == "Blue Yonder" for p in passages)


def test_retrieval_returns_nothing_for_gibberish(seeded):
    assert retrieve_passages(seeded, "zzz") == []


# ─── ingestion ─────────────────────────────────────────────────────────────

def test_text_extraction_normalises_whitespace():
    assert ingest.extract_text(b"a  b\r\n\r\n\r\nc", "n.txt") == "a b\n\nc"


def test_csv_becomes_readable_rows():
    assert ingest.extract_text(b"a,b\n1,2\n", "n.csv") == "a | b\n1 | 2"


def test_unsupported_extension_is_rejected_clearly():
    with pytest.raises(ingest.ExtractionError, match="Cannot read"):
        ingest.extract_text(b"data", "virus.exe")


def test_empty_file_is_rejected():
    with pytest.raises(ingest.ExtractionError):
        ingest.extract_text(b"", "n.txt")


def test_docx_roundtrip():
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Kinaxis is strong in manufacturing.")
    buffer = io.BytesIO()
    document.save(buffer)
    text = ingest.extract_text(buffer.getvalue(), "a.docx")
    assert "manufacturing" in text


def test_xlsx_roundtrip():
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    workbook.active.append(["Client", "Vertical"])
    workbook.active.append(["GroceryCo", "Grocery"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    assert "GroceryCo" in ingest.extract_text(buffer.getvalue(), "a.xlsx")


def test_chunks_overlap_and_cover_the_text():
    text = "word " * 800
    chunks = ingest.chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= ingest.CHUNK_CHARS + 40 for c in chunks)


def test_short_text_is_a_single_chunk():
    assert ingest.chunk_text("short") == ["short"]


# ─── link rewriting ────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,fragment", [
    ("https://docs.google.com/document/d/ABC/edit", "export?format=txt"),
    ("https://docs.google.com/spreadsheets/d/ABC/edit", "export?format=csv"),
    ("https://drive.google.com/file/d/ABC/view", "export=download"),
])
def test_share_links_rewrite_to_direct_downloads(url, fragment):
    rewritten = direct_url(url)
    assert rewritten and fragment in rewritten[0]


def test_unknown_host_is_not_rewritten():
    assert direct_url("https://evil.example.com/file") is None


# ─── storage ───────────────────────────────────────────────────────────────

def test_entry_is_stored_under_the_canonical_competitor(conn):
    entry = db.create_entry(conn, {"competitor": "o9", "title": "T",
                                   "category": "battlecard"})
    assert entry["competitor"] == "o9 Solutions"


def test_delete_removes_the_entry_and_its_index(conn):
    entry = db.create_entry(conn, {"competitor": "o9", "title": "T",
                                   "category": "battlecard",
                                   "content": "uniquetoken here"},
                            chunks=["uniquetoken here"])
    assert db.delete_entry(conn, entry["id"]) is True
    assert search(conn, "uniquetoken")["total"] == 0
    assert db.stats(conn)["chunks"] == 0
