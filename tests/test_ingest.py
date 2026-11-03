import asyncio
import json
from pathlib import Path

import httpx
import openpyxl
import pymupdf
import pytest

from backend.config import Settings
from backend.knowledge_models import Candidate, PageExtraction, PageVerification
from backend.knowledge_report import render_report
from backend.knowledge_store import (SOURCES, active_directory, canonical_candidate, digest, extract_pages, import_methods,
                                     inventory, publish, read_json, validate_corpus, write_json)
from backend.main import create_app
from backend.retrieval import fuse, make_segments
from backend.provider import ProviderError
from tests.corpus_fixture import FakeEmbedder, make_corpus, rehash


@pytest.fixture
def supplied(tmp_path):
    directory = tmp_path / "sources"
    directory.mkdir()
    for sid, (name, role) in SOURCES.items():
        path = directory / name
        if path.suffix == ".pdf":
            doc = pymupdf.open()
            for number in range(6 if sid == "S01" else 1):
                page = doc.new_page()
                page.insert_text((40, 60), f"{sid} page {number + 1}. Optical path is 1-6 um.")
            doc.save(path)
            doc.close()
        elif path.suffix == ".xlsx":
            from backend.knowledge_store import METHOD_COLUMNS
            book = openpyxl.Workbook()
            sheet = book.active
            sheet.title = "method_comparison"
            sheet.append(METHOD_COLUMNS)
            for i in range(19):
                sheet.append([1, "IR spectroscopy", f"geometry {i}", "absorption", "liquid", "1-6 um", "average", "high", "high"])
            notes = book.create_sheet("notes")
            for i in range(7):
                notes.append([f"Original note {i}"])
            book.save(path)
        else:
            path.write_text("https://example.com/laboratory/" if sid == "S06" else "Excluded development content", encoding="utf-8")
    (directory / "customer_scenarios_for_final_evaluation.txt").write_text("Hold-out scenario", encoding="utf-8")
    return directory


def candidate(**changes):
    return Candidate.model_validate({"section": "Optical geometry", "content_kind": "verbatim_text", "evidence_scope": "general_method",
        "spans": [{"block_id": "b001", "quote": "Optical path is 1-6 um."}], "region": None, "transcription": None,
        "interpretation": None, "facts": [], "tags": ["ATR"], "issues": [], **changes})


def source_page():
    return {"source_id": "S01", "file_name": "test.pdf", "source_sha256": "a" * 64, "page": 6, "role": "technical",
            "image": "assets/page.jpg", "blocks": [{"block_id": "b001", "text": "Optical path is 1-6 um.", "bbox": [1, 2, 3, 4]}]}


def test_inventory_page_counts_hashes_and_exclusions(supplied, tmp_path):
    entries = inventory(supplied)
    by_id = {s["source_id"]: s for s in entries}
    assert by_id["S01"]["page_count"] == 6
    assert not by_id["S05"]["technical_eligible"] and not by_id["S06"]["url_fetched"]
    assert not by_id["D01_DOC"]["technical_eligible"]
    assert next(s for s in entries if s["file_name"].startswith("customer_scenarios"))["role"] == "excluded_unknown"
    pages = extract_pages(supplied, entries, tmp_path / "extracted")
    assert {p["page"] for p in pages if p["source_id"] == "S01"} == set(range(1, 7))
    assert all((tmp_path / "extracted" / p["image"]).is_file() for p in pages)


def test_workbook_preserves_all_cells_notes_and_dual_provenance(supplied):
    entries = inventory(supplied)
    rows, notes = import_methods(supplied, entries)
    assert len(rows) == 19 and len(notes) == 7
    assert [r["row"] for r in rows] == list(range(2, 21))
    assert len({r["evidence_id"] for r in rows}) == 19
    assert rows[0]["raw_values"]["optical_path_or_depth"] == "1-6 um"
    assert rows[0]["raw_values"]["sensitivity"] == "average"
    assert rows[0]["underlying_citation"]["source_id"] == "S01"
    assert rows[0]["underlying_citation"]["page"] == 6
    assert notes[6]["text"] == "Original note 6"
    again, _ = import_methods(supplied, entries)
    assert rows == again


def test_source_spans_ids_revisions_and_model_cannot_approve():
    p = source_page()
    verdict = {"status": "supported", "reason": "Matches source"}
    r = canonical_candidate(candidate(), p, verdict, "extract-v1")
    assert r["text"] == "Optical path is 1-6 um." and r["retrieval_eligible"]
    assert r["source_spans"][0]["start"] == 0
    assert r["human_review_status"] == "not_reviewed"
    assert r == canonical_candidate(candidate(), p, verdict, "extract-v1")
    changed = canonical_candidate(candidate(tags=["MIR"]), p, verdict, "extract-v2")
    assert changed["evidence_id"] == r["evidence_id"] and changed["revision"] != r["revision"]
    bad = canonical_candidate(candidate(spans=[{"block_id": "b001", "quote": "Accuracy is guaranteed"}]), p, verdict, "v1")
    assert not bad["retrieval_eligible"] and bad["validation_status"] == "flagged"
    business = canonical_candidate(candidate(evidence_scope="business_context"), {**p, "role": "business"}, verdict, "v1")
    assert not business["retrieval_eligible"]


def test_visual_ambiguity_and_quantity_units_are_not_silently_accepted():
    p = source_page()
    figure = candidate(content_kind="figure_transcription", spans=[], transcription="Visible range 1-6 um.",
        region={"x0": .1, "y0": .2, "x1": .7, "y1": .8, "label": "Range chart"})
    assert canonical_candidate(figure, p, {"status": "supported"}, "v1")["retrieval_eligible"]
    assert not canonical_candidate(figure, p, {"status": "ambiguous"}, "v1")["retrieval_eligible"]
    bad = candidate(facts=[{"category": "geometry", "statement": "Optical path", "support_quotes": ["Optical path is 1-6 um."],
        "quantities": [{"label": "depth", "value": "1-6", "unit": "mm", "kind": "optical_path_or_depth", "source_quote": "1-6 um"}]}])
    assert not canonical_candidate(bad, p, {"status": "supported"}, "v1")["retrieval_eligible"]
    word = candidate(facts=[{"category": "geometry", "statement": "Optical path", "support_quotes": ["Optical path is 1-6 um."],
        "quantities": [{"label": "depth", "value": "path", "unit": None, "kind": "optical_path_or_depth", "source_quote": "Optical path is 1-6 um."}]}])
    assert "Quantity value is not numerical" in canonical_candidate(word, p, {"status": "supported"}, "v1")["issues"]












def test_validation_rejects_tampering_excluded_records_and_wrong_pages(tmp_path):
    make_corpus(tmp_path)
    assert validate_corpus(tmp_path, deep=True)["eligible_methods"] == 19
    path = tmp_path / "passages.jsonl"
    record = json.loads(path.read_text())
    record["page"] = 7
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        validate_corpus(tmp_path)
    rehash(tmp_path)
    with pytest.raises(KeyError):
        validate_corpus(tmp_path)
    record.update(page=6, evidence_scope="business_context")
    path.write_text(json.dumps(record), encoding="utf-8")
    rehash(tmp_path)
    with pytest.raises(ValueError, match="Ineligible"):
        validate_corpus(tmp_path)


def test_segments_do_not_truncate_or_break_sentences_and_fusion_deduplicates():
    record = {"evidence_id": "test", "section": "Geometry", "text": "One sample. Two samples. Depth 1-6 um.", "retrieval_eligible": True}
    segments = make_segments([record, {**record, "retrieval_eligible": False}], FakeEmbedder.count)
    assert len(segments) == 1 and "Depth 1-6 um." in segments[0]["text"]
    with pytest.raises(ValueError, match="indivisible"):
        make_segments([{**record, "text": "Long sentence " * 500}], FakeEmbedder.count)
    fused = fuse(["a", "b"], ["b", "b", "c"])
    assert fused[0][0] == "b" and len(fused) == 3


def test_whitespace_matching_never_changes_values_or_units():
    from backend.knowledge_store import anchored_quote
    assert anchored_quote("Depth 1-6\n um", "Depth 1-6 um") == "Depth 1-6\n um"
    assert anchored_quote("Depth 1-6 um", "Depth 1-6 mm") is None
    assert anchored_quote("Depth 1-6 um", "Depth 10-60 um") is None






def test_publication_switches_pointer_and_preserves_previous_on_failure(tmp_path):
    root = tmp_path / "knowledge"
    staged = root / ".staging" / "build"
    manifest, _, _ = make_corpus(staged)
    write_json(staged / "validation_report.json", {"status": "passed"})
    final = publish(root, staged, manifest)
    assert active_directory(root) == final
    assert validate_corpus(final)["status"] == "passed"
    failed = root / ".staging" / "failed"
    failed.mkdir()
    write_json(failed / "build_status.json", {"status": "failed"})
    assert active_directory(root) == final


def test_report_escapes_source_content_and_api_restricts_files(tmp_path):
    directory = tmp_path / "versions" / ("corpus-" + "a" * 20)
    make_corpus(directory)
    path = directory / "passages.jsonl"
    record = json.loads(path.read_text())
    record["section"] = '</script><script>alert("bad")</script>'
    path.write_text(json.dumps(record), encoding="utf-8")
    output = render_report(directory)
    html = output.read_text(encoding="utf-8")
    assert record["section"] not in html and "\\u003c/script" in html
    config = Settings(_env_file=None, corpus_dir=tmp_path)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(config)), base_url="http://test") as client:
            prefix = "/api/knowledge/versions/" + directory.name + "/"
            assert (await client.get(prefix + "review.html")).status_code == 200
            assert (await client.get(prefix + "assets/p1.jpg")).status_code == 200
            assert (await client.get(prefix + "source_manifest.json")).status_code == 404
            assert (await client.get(prefix + "../../.env")).status_code == 404
            assert (await client.get("/api/knowledge/report")).status_code == 404
    asyncio.run(run())
