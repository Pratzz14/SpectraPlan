"""Development input and batch-runner contracts."""

from pathlib import Path
import asyncio
import json

import pytest

from evaluation.run_evaluation import (
    DEVELOPMENT_INPUT,
    FINAL_CASE_IDS,
    load_development_cases,
    load_final_cases,
    prepare_final_input,
)
import evaluation.run_evaluation as runner
from backend.knowledge_store import digest, write_json


def test_development_inputs_match_supplied_source_and_cover_all_cases():
    source, cases = load_development_cases()
    assert source["source_file"] == "AFS_Examples_and_Reference.docx"
    assert [case["case_id"] for case in cases] == [f"D{index:02d}" for index in range(1, 9)]
    assert all(case["description"] and case["source_paragraphs"] for case in cases)


def test_development_source_hash_mismatch_is_rejected(tmp_path):
    target = tmp_path / "development.json"
    target.write_text(Path(DEVELOPMENT_INPUT).read_text(encoding="utf-8").replace(
        "5511a7aaf972613b6c9dcb0b8425c68a4399cc0444eae542e516d6a5be9b978e",
        "0" * 64), encoding="utf-8")
    with pytest.raises(ValueError, match="source hash"):
        load_development_cases(target)


def test_final_input_preserves_original_h01_to_h06_text(tmp_path):
    source = tmp_path / "customer_scenarios_for_final_evaluation.txt"
    source.write_text(
        "H01\nFirst enquiry line.\nSecond line.\n\nH02: Second enquiry.\n\n"
        "H03\nThird enquiry.\nH04\nFourth enquiry.\nH05\nFifth enquiry.\nH06\nSixth enquiry.\n",
        encoding="utf-8", newline="",
    )
    prepared = tmp_path / "final.json"
    data, cases = prepare_final_input(source, prepared)
    assert {case["case_id"] for case in cases} == FINAL_CASE_IDS
    loaded, loaded_cases = load_final_cases(prepared)
    assert loaded["source_sha256"] == data["source_sha256"]
    assert loaded_cases[0]["description"] == "First enquiry line.\nSecond line."
    assert loaded_cases[1]["description"] == "Second enquiry."


def test_final_input_source_change_is_rejected(tmp_path):
    source = tmp_path / "scenarios.txt"
    source.write_text("\n".join([f"H0{i}\nEnquiry {i}." for i in range(1, 7)]), encoding="utf-8")
    prepared = tmp_path / "final.json"
    prepare_final_input(source, prepared)
    source.write_text(source.read_text(encoding="utf-8") + "\nChanged", encoding="utf-8")
    with pytest.raises(ValueError, match="source hash"):
        load_final_cases(prepared)


def test_final_parser_retains_crlf_indent_and_trailing_spaces(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes("\r\n".join(f"H0{i}\r\n  Enquiry {i}.  \r\nSecond line.  \r\n" for i in range(1, 7)).encode())
    _, cases = prepare_final_input(source, tmp_path / "final.json")
    assert cases[0]["description"] == "  Enquiry 1.  \r\nSecond line.  "
    content = source.read_bytes().decode()
    assert all(content[slice(*case["source_span"])] == case["description"] for case in cases)


def test_final_parser_removes_heading_separators(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("\n".join(
        f"H0{i} | Title {i}\n{'=' * 78}\nEnquiry {i}."
        for i in range(1, 7)
    ), encoding="utf-8")
    _, cases = prepare_final_input(source, tmp_path / "final.json")
    assert cases[0]["description"] == "Enquiry 1."
    assert all("=" not in case["description"] for case in cases)


@pytest.fixture
def final_batch(tmp_path, monkeypatch):
    """Real public route and history, synthetic provider and retrieval only."""
    from tests.test_assessment import DESCRIPTION, draft
    from tests.test_assessment_api import provider_for, mock_retrieval
    from tests.test_extraction import powder, wire_for

    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "RETRIEVAL_VERSION", "test")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/source.py").write_text("# synthetic execution source\n", encoding="utf-8")
    corpus = tmp_path / "knowledge"
    write_json(corpus / "current.json", {"corpus_version": "corpus-test", "directory": "versions/corpus-test"})
    write_json(corpus / "versions/corpus-test/source_manifest.json", {"corpus_version": "corpus-test"})
    write_json(corpus / "versions/corpus-test/index_manifest.json", {"corpus_version": "corpus-test"})
    source = tmp_path / "scenarios.txt"
    source.write_text("\n".join(f"H0{i}\n{DESCRIPTION}" for i in range(1, 7)), encoding="utf-8")
    input_path = tmp_path / "final.json"
    prepare_final_input(source, input_path)
    adapter, calls = provider_for([wire_for(powder().model_dump()), draft()] * 6, corpus_dir=corpus)
    monkeypatch.setattr("backend.agent.Provider", lambda settings: adapter)
    mock_retrieval(monkeypatch)
    monkeypatch.setattr(runner, "audit_final_inputs", lambda *args: {"findings": [], "scope": "synthetic fixture"})
    requests, responses = [], []
    original_client = runner.httpx.AsyncClient

    class RecordingClient(original_client):
        async def post(self, url, **kwargs):
            assessment_request = url == "/api/assess"
            if assessment_request:
                requests.append(kwargs["json"])
            response = await super().post(url, **kwargs)
            if assessment_request:
                responses.append(response.content)
            return response

    monkeypatch.setattr(runner.httpx, "AsyncClient", RecordingClient)
    manifest, code = asyncio.run(runner.run_cases(adapter.settings, input_path=input_path,
        output_dir=tmp_path / "outputs/runs", evaluation_kind="final"))
    assert code == 0
    manifest_path = next((tmp_path / "outputs/runs").glob("*/manifest.json"))
    return manifest_path, manifest, requests, responses


def test_final_runner_offline_verification_and_publication(final_batch, monkeypatch):
    path, manifest, requests, responses = final_batch
    assert all(set(request) == {"description"} for request in requests)
    for record, response in zip(manifest["cases"], responses):
        assert (path.parent / record["output_path"]).read_bytes() == response
    assert runner.verify_manifest(path)[1] == []
    published, code = runner.publish_batch(path)
    assert code == 0
    assert runner.verify_manifest(runner.PROJECT_ROOT / "outputs/run_manifest.json")[1] == []
    for record, response in zip(published["cases"], responses):
        assert (runner.PROJECT_ROOT / f"outputs/{record['case_id']}.json").read_bytes() == response
    # Portable verification does not need source originals or the history DB.
    (runner.PROJECT_ROOT / "scenarios.txt").unlink()
    (path.parent / "explainability.sqlite").unlink()
    assert runner.verify_manifest(path)[1] == []


@pytest.mark.parametrize("defect", ["duplicate", "configuration", "request", "trace", "evidence", "outcome", "location", "hash", "drift"])
def test_final_verifier_rejects_tampering(final_batch, defect):
    path, manifest, _, _ = final_batch
    record = manifest["cases"][0]
    if defect == "duplicate":
        manifest["cases"].append(record.copy())
    elif defect == "configuration":
        record["configuration_id"] = "different"
    elif defect == "request":
        request_path = path.parent / record["request_path"]
        write_json(request_path, {"description": "modified", "clarification_answers": []})
        record["request_sha256"] = runner.file_hash(request_path)
    elif defect == "trace":
        (path.parent / record["trace_path"]).unlink()
    elif defect == "evidence":
        evidence_path = path.parent / record["evidence_path"]
        write_json(evidence_path, [])
        record["evidence_sha256"] = runner.file_hash(evidence_path)
    elif defect == "outcome":
        record["http_status"] = 503
    elif defect == "location":
        record["output_path"] = "../another-batch/H01.json"
    elif defect == "hash":
        (path.parent / record["output_path"]).write_bytes(b"{}")
    else:
        manifest["configuration_drift"] = True
    write_json(path, manifest)
    assert runner.verify_manifest(path)[1]
    assert runner.publish_batch(path)[1] == 1


def test_final_source_missing_does_not_create_input(tmp_path):
    output = tmp_path / "final.json"
    with pytest.raises(ValueError, match="unavailable"):
        prepare_final_input(tmp_path / "missing.txt", output)
    assert not output.exists()
