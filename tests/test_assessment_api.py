"""F06 public contracts and failures; provider calls are mocked unless explicitly live."""

import asyncio
import json
from pathlib import Path
import threading
import time

import httpx
import pytest
from pydantic import ValidationError

from backend.pipelines.assessment.pipeline import assess_case, synthesize_assessment
from backend.services.search.evidence import CorpusUnavailable, load_snapshot
from tests.auth_helpers import create_app
from backend.schemas.models import AssessmentRun, ProposedSetting, MeasurementContext
from backend.providers.provider import Provider, ProviderError
from backend.pipelines.assessment.validation import (
    AssessmentValidationError, authenticate_ledger,
    validate_final, validate_synthesis, validation_groups,
)
from tests.test_assessment import DESCRIPTION, EID, config, draft, ledger
from tests.test_extraction import facts_for, powder, wire_for


def provider_for(responses, **settings):
    calls = []
    responses = iter(responses)

    def handle(request):
        calls.append(json.loads(request.content))
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        content = response if isinstance(response, str) else json.dumps(response)
        return httpx.Response(200, json={"model": "actual-model", "usage": {"total_tokens": len(calls)},
            "choices": [{"finish_reason": "stop", "message": {"content": content}}]})

    return Provider(config(**settings), transport=httpx.MockTransport(handle)), calls


def mock_retrieval(monkeypatch, result=None, error=None):
    """Unit seam; canonical corpus authentication is covered separately below."""
    monkeypatch.setattr("backend.pipelines.assessment.pipeline.authenticate_ledger", lambda *args, **kwargs: None)

    def retrieve(self, facts, deadline):
        if error:
            raise error
        return result if result is not None else ledger()

    monkeypatch.setattr("backend.services.search.retrieval.CaseRetrievalService.retrieve_case", retrieve)


def post(monkeypatch, adapter, body):
    monkeypatch.setattr("backend.pipelines.assessment.pipeline.Provider", lambda settings: adapter)

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(adapter.settings)),
                                     base_url="http://test") as client:
            return await client.post("/api/assess", json=body)

    return asyncio.run(request())


@pytest.mark.parametrize("body", [
    {}, {"description": ""}, {"description": " \n\t"}, {"description": 5},
    {"description": "x" * 8001}, {"description": DESCRIPTION, "fact_overrides": {}},
    {"description": DESCRIPTION, "extra": True},
])
def test_input_rejected_before_calls(monkeypatch, body):
    adapter, calls = provider_for([])
    response = post(monkeypatch, adapter, body)
    assert response.status_code == 422 and not calls


@pytest.mark.parametrize("length,limit,status", [(8000, 8000, 200), (51, 50, 422)])
def test_description_limit_and_original_whitespace(monkeypatch, length, limit, status):
    text = " " + "x" * (length - 2) + "\n"
    facts = facts_for(text, {"context_id": "stream_1", "label": "x"})
    adapter, calls = provider_for([wire_for(facts.model_dump()), draft(empty=True)],
                                  assessment_max_description_chars=limit)
    mock_retrieval(monkeypatch, ledger(empty=True))
    response = post(monkeypatch, adapter, {"description": text, "fact_overrides": None})
    assert response.status_code == status
    if status == 200:
        assert json.loads(calls[0]["messages"][1]["content"])["description"] == text
        assert response.json()["run_status"] == "complete"


@pytest.mark.parametrize("case_id", ["D01", "D02"])
def test_development_cases_through_public_api(monkeypatch, case_id):
    cases = json.loads(Path("evaluation/development.json").read_text(encoding="utf-8"))["cases"]
    text = next(c["description"] for c in cases if c["case_id"] == case_id)
    context = ({"context_id": "stream_1", "label": "powder blend", "sample_phase": "powder",
                "target_analytes": ["API concentration"]} if case_id == "D01" else
               {"context_id": "stream_1", "label": "opaque, concentrated milk product",
                "appearance": "opaque", "target_analytes": ["fat", "protein"],
                "process_constraints": ["Product temperature and texture vary during production."]})
    facts = facts_for(text, context)
    from backend.pipelines.assessment.validation import _validation_options
    data = draft()
    data["experiment"]["validation"] = _validation_options(facts)[0]
    data["case_summary"] = ("The customer requests API concentration monitoring in a powder blend."
                            if case_id == "D01" else "The customer requests fat and protein monitoring in opaque milk.")
    retrieved = ledger()
    if case_id == "D02":
        retrieved.evidence[0].evidence.text = "Synthetic milk NIR reflection screening example."
        data["recommendations"][0]["rationale"]["text"] = "Source excerpt (application_example): Synthetic milk NIR reflection screening example."
    adapter, calls = provider_for([wire_for(facts.model_dump()), data])
    mock_retrieval(monkeypatch, retrieved)
    response = post(monkeypatch, adapter, {"description": text})
    assert response.status_code == 200
    result = AssessmentRun.model_validate(response.json())
    assert result.run_status == "complete" and result.errors == [] and len(calls) == 2
    assert result.assessment.source_index[0].evidence_id == result.retrieval.evidence[0].evidence.evidence_id
    assert result.metadata.returned_models == {"extraction": "actual-model", "synthesis": "actual-model"}
    assert result.metadata.repair_counts == {"extraction": 0, "synthesis": 0}
    assert result.assessment.experiment.validation_groups[0].independent_unit == "run"


@pytest.mark.parametrize("failure,status", [
    (httpx.Response(503), 503),
    (httpx.ReadTimeout("private network detail"), 504),
    ("not json", 502),
])
def test_failures_without_validated_facts_have_http_error_and_envelope(monkeypatch, failure, status):
    adapter, calls = provider_for([failure, failure])
    response = post(monkeypatch, adapter, {"description": DESCRIPTION})
    assert response.status_code == status
    result = AssessmentRun.model_validate(response.json())
    assert result.run_status == "incomplete" and result.facts is None and result.assessment is None
    assert result.errors[0].stage == "extraction"
    assert result.metadata.corpus_version is None
    assert "private network detail" not in response.text and "test-secret" not in response.text
    assert len(calls) == (2 if status == 502 else 1)


@pytest.mark.parametrize("failure", ["not json", httpx.Response(503), httpx.ReadTimeout("private detail")])
def test_later_provider_failures_return_200_incomplete(monkeypatch, failure):
    adapter, calls = provider_for([wire_for(powder().model_dump()), failure, failure])
    mock_retrieval(monkeypatch)
    response = post(monkeypatch, adapter, {"description": DESCRIPTION})
    result = AssessmentRun.model_validate(response.json())
    assert response.status_code == 200 and result.run_status == "incomplete"
    assert result.facts == powder() and result.assessment is None and result.retrieval is not None
    assert result.errors[0].stage == "synthesis"
    assert "private detail" not in response.text
    assert result.metadata.corpus_version == "corpus-test"
    assert len(calls) == (3 if failure == "not json" else 2)


def test_unavailable_corpus_retains_extraction_and_never_synthesizes(monkeypatch):
    adapter, calls = provider_for([wire_for(powder().model_dump())])
    mock_retrieval(monkeypatch, error=CorpusUnavailable("private file path"))
    response = post(monkeypatch, adapter, {"description": DESCRIPTION})
    data = response.json()
    assert response.status_code == 200 and data["assessment"] is None and data["retrieval"] is None
    assert data["facts"] and data["errors"][0]["stage"] == "retrieval"
    assert data["errors"][0]["code"] == "corpus_unavailable" and len(calls) == 1
    assert "private file path" not in response.text


def test_evidence_gap_can_complete_with_characterization(monkeypatch):
    facts = facts_for("Assess our product.", {"context_id": "stream_1", "label": "product"})
    adapter, _ = provider_for([wire_for(facts.model_dump()), draft(empty=True)])
    mock_retrieval(monkeypatch, ledger(empty=True))
    response = post(monkeypatch, adapter, {"description": "Assess our product."})
    result = AssessmentRun.model_validate(response.json())
    assert result.run_status == "complete" and result.assessment.decision_status == "insufficient_information"
    assert result.assessment.recommendations == [] and result.assessment.source_index == []
    experiment = result.assessment.experiment
    assert experiment.validation_groups[0].study_type == "characterization"
    assert any("before analyte calibration" in x for x in experiment.measurements)
    assert all(c.threshold is None for c in experiment.acceptance_criteria)
    assert any("acceptance threshold" in x for x in experiment.open_items)


@pytest.mark.parametrize("bad", ["not-json", "evidence", "provenance"])
def test_one_synthesis_repair_uses_identical_evidence_schema_and_deadline(bad):
    invalid = draft()
    if bad == "evidence":
        invalid["recommendations"][0]["rationale"]["evidence_ids"] = ["invented"]
    elif bad == "provenance":
        invalid["recommendations"][0]["spectral_range"].update(
            kind="nominal_method_range", interval="10-20 nm", evidence_ids=[EID])
    else:
        invalid = "not JSON"
    adapter, calls = provider_for([invalid, draft()])
    stop = time.monotonic() + 15
    deadlines = []
    original = adapter.structured

    async def structured(*args, **kwargs):
        deadlines.append(kwargs["deadline"])
        return await original(*args, **kwargs)

    adapter.structured = structured
    result = asyncio.run(synthesize_assessment(powder(), ledger(), provider=adapter, deadline=stop))
    assert result.recommendations and deadlines == [stop, stop]
    assert len(calls) == 2 and adapter.repair_counts["synthesis"] == 1
    assert calls[0]["response_format"] == calls[1]["response_format"]
    assert calls[0]["messages"] == calls[1]["messages"][:2]
    assert "validation_errors" in json.loads(calls[1]["messages"][-1]["content"])


def test_extraction_and_synthesis_have_separate_repair_budgets(monkeypatch):
    adapter, calls = provider_for(["not-json", wire_for(powder().model_dump()), "not-json", draft()])
    mock_retrieval(monkeypatch)
    response = post(monkeypatch, adapter, {"description": DESCRIPTION})
    assert response.json()["run_status"] == "complete" and len(calls) == 4
    assert response.json()["metadata"]["repair_counts"] == {"extraction": 1, "synthesis": 1}


def test_deadline_expiry_prevents_synthesis_repair():
    adapter, calls = provider_for([])
    clock = [10.0]

    async def invalid(*args, **kwargs):
        calls.append(kwargs)
        clock[0] = 12.0
        raise ProviderError("provider_invalid_response", "invalid", 502)

    adapter.structured = invalid
    from unittest.mock import patch
    with patch("backend.pipelines.assessment.pipeline.time.monotonic", lambda: clock[0]):
        with pytest.raises(ProviderError) as error:
            asyncio.run(synthesize_assessment(powder(), ledger(), provider=adapter, deadline=11.0))
    assert error.value.http_status == 504 and len(calls) == 1
    assert adapter.repair_counts["synthesis"] == 0


def test_slow_retrieval_is_bounded_and_late_result_is_discarded(monkeypatch):
    adapter, calls = provider_for([wire_for(powder().model_dump())])
    released, entered = threading.Event(), threading.Event()
    authenticated = []
    monkeypatch.setattr("backend.pipelines.assessment.pipeline.authenticate_ledger", lambda *args: authenticated.append(True))

    class SlowRetrieval:
        def retrieve_case(self, facts, deadline):
            entered.set()
            released.wait(2)
            return ledger()

    async def run():
        # Warm extraction once, then set a generous enough budget for scheduling.
        async def extract(*args, **kwargs):
            return powder()
        monkeypatch.setattr("backend.pipelines.assessment.pipeline.extract_case", extract)
        start = time.monotonic()
        try:
            result = await assess_case(DESCRIPTION, provider=adapter, retrieval_service=SlowRetrieval(),
                                       deadline=start + .15)
            assert entered.is_set() and not released.is_set()
            assert time.monotonic() - start < 1
            assert result.run_status == "incomplete" and result.retrieval is None and result.assessment is None
            assert result.errors[0].stage == "retrieval" and result.errors[0].http_status == 504
        finally:
            released.set()

    asyncio.run(run())
    assert not calls and not authenticated


def test_unexpected_programming_failure_stays_500(monkeypatch):
    adapter, _ = provider_for([])

    async def broken(*args, **kwargs):
        raise RuntimeError("programming defect")

    monkeypatch.setattr("backend.pipelines.assessment.pipeline.extract_case", broken)
    with pytest.raises(RuntimeError, match="programming defect"):
        post(monkeypatch, adapter, {"description": DESCRIPTION})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_proposed_settings_reject_nonfinite_quantities(value):
    with pytest.raises(ValidationError):
        ProposedSetting(context_ids=["stream_1"], name="replicate count", value=value, unit=None)


def test_patient_grouping_is_context_specific_and_takes_precedence_over_specimens():
    facts = facts_for("patient tissue specimen; manufacturing batch", {
        "context_id": "stream_1", "label": "patient tissue specimen"}, {
        "context_id": "stream_2", "label": "manufacturing batch"})
    groups = validation_groups(facts)
    assert [g["independent_unit"] for g in groups] == ["patient", "batch"]


def test_customer_thresholds_are_copied_with_provenance_and_missing_ones_stay_open():
    text = "powder moisture; error 2%; respond in 3 seconds"
    facts = facts_for(text, {"context_id": "stream_1", "label": "powder", "sample_phase": "powder",
        "target_analytes": ["moisture"], "required_error": "2%", "response_time_raw": "3 seconds", "response_time_s": 3.0})
    adapter, _ = provider_for([draft()])
    result = asyncio.run(synthesize_assessment(facts, ledger(), provider=adapter))
    criteria = result.experiment.acceptance_criteria
    assert criteria[0].threshold == "2%" and criteria[0].requirement_path == "/contexts/0/required_error"
    assert criteria[1].threshold == "3 seconds"
    assert criteria[2].threshold is None and criteria[2].origin == "unknown"
    assert "2%" in result.experiment.decision_criteria and "3 seconds" in result.experiment.decision_criteria
    changed = result.model_copy(deep=True)
    changed.experiment.acceptance_criteria[0].threshold = "5%"
    with pytest.raises(AssessmentValidationError, match="Assessment failed") as error:
        validate_final(changed, facts, ledger())
    assert any("threshold_override" in x for x in error.value.errors)


@pytest.mark.parametrize("mutation,rule", [
    ("cross_stream", "cross_context_reference"),
    ("excitation", "excitation_as_coverage"),
    ("configuration", "nominal_range_as_configuration"),
    ("threshold", "threshold_override"),
])
def test_configured_structured_conflicts(mutation, rule):
    facts, retrieved, data = powder(), ledger(), draft()
    if mutation == "cross_stream":
        facts.contexts.append(MeasurementContext(context_id="stream_2", label="milk"))
        data["recommendations"][0]["context_ids"] = ["stream_2"]
    elif mutation in {"excitation", "configuration"}:
        retrieved.evidence[0].evidence.text += (" Raman excitation is 785 nm." if mutation == "excitation" else " NIR spectral range is 100-200 nm.")
        data["recommendations"][0]["spectral_range"].update(kind="source_configuration_range",
            interval="785-785 nm" if mutation == "excitation" else "100-200 nm", evidence_ids=[EID])
    else:
        data["experiment"]["proposed_settings"] = [{"context_ids": ["stream_1"], "name": "required error",
            "value": 2.0, "unit": "%", "origin": "proposed"}]
    with pytest.raises(AssessmentValidationError) as error:
        validate_synthesis(data, facts, retrieved)
    assert any(rule in x for x in error.value.errors)


def test_published_corpus_authentication_checks_all_record_fields(tmp_path):
    from tests.corpus_fixture import make_corpus
    from tests.test_retrieval import set_version
    version = "corpus-" + "a" * 20
    directory = tmp_path / "versions" / version
    make_corpus(directory)
    set_version(directory, version)
    snapshot = load_snapshot(tmp_path, version)
    retrieved = ledger()
    retrieved.corpus_version = version
    retrieved.evidence[0].evidence = snapshot.resolve(EID)
    authenticate_ledger(powder(), retrieved, tmp_path)
    for field, value in [("page", 1), ("revision", "wrong"), ("text", "altered text"), ("workbook_notes", [{"text": "altered"}])]:
        tampered = retrieved.model_copy(deep=True)
        setattr(tampered.evidence[0].evidence, field, value)
        with pytest.raises(CorpusUnavailable):
            authenticate_ledger(powder(), tampered, tmp_path)


def test_envelope_invariants_and_offline_evidence(monkeypatch):
    adapter, _ = provider_for([wire_for(powder().model_dump()), draft()])
    mock_retrieval(monkeypatch)
    response = post(monkeypatch, adapter, {"description": DESCRIPTION})
    valid = response.json()
    assert AssessmentRun.model_validate_json(response.text).assessment
    for update in [{"run_status": "incomplete"}, {"assessment": None}, {"facts": None},
                   {"errors": [{"code": "failed", "stage": "synthesis", "message": "failed", "http_status": 502}]}]:
        with pytest.raises(ValidationError):
            AssessmentRun.model_validate({**valid, **update})
    record = valid["retrieval"]["evidence"][0]["evidence"]
    assert record["text"] and record["source_sha256"] and record["revision"]
    assert record["human_review_status"] == "not_reviewed"


def test_missing_input_provenance_exhausts_extraction_repair(monkeypatch):
    invalid = wire_for(powder().model_dump())
    invalid["contexts"][0]["sample_phase"]["input_quote"] = "not in the enquiry"
    adapter, calls = provider_for([invalid, invalid])
    response = post(monkeypatch, adapter, {"description": DESCRIPTION})
    assert response.status_code == 502 and len(calls) == 2
    assert response.json()["facts"] is None and response.json()["assessment"] is None
    assert response.json()["errors"][0]["code"] == "extraction_invalid_response"
    assert "not in the enquiry" not in response.text


def test_configuration_range_requires_and_accepts_structured_equipment_quantity():
    retrieved = ledger(text="Synthetic powder NIR reflection screening example. Instrument NIR spectral range is 100-200 nm.")
    retrieved.evidence[0].evidence = retrieved.evidence[0].evidence.model_copy(update={"facts": [{
        "category": "equipment", "statement": "Instrument NIR spectral range is 100-200 nm.",
        "support_quotes": ["Instrument NIR spectral range is 100-200 nm."], "quantities": [
            {"label": "coverage", "kind": "spectral_range", "value": "100-200 nm", "unit": "nm",
             "source_quote": "Instrument NIR spectral range is 100-200 nm."}]}]})
    data = draft()
    data["recommendations"][0]["spectral_range"].update(
        kind="source_configuration_range", interval="100-200 nm", evidence_ids=[EID])
    adapter, _ = provider_for([data])
    result = asyncio.run(synthesize_assessment(powder(), retrieved, provider=adapter))
    assert result.recommendations[0].spectral_range.kind == "source_configuration_range"


def test_patient_relationship_in_single_context_quote_prevents_specimen_split():
    text = "Take multiple tissue specimens per patient."
    facts = facts_for(text, {"context_id": "stream_1", "label": "tissue specimens"})
    assert validation_groups(facts)[0]["independent_unit"] == "patient"


def test_ambiguous_patient_relationship_requires_unit_clarification():
    text = "tissue specimens; milk; one stream has multiple specimens per patient"
    facts = facts_for(text, {"context_id": "stream_1", "label": "tissue specimens"},
                      {"context_id": "stream_2", "label": "milk"})
    assert [g["independent_unit"] for g in validation_groups(facts)] == ["unresolved", "unresolved"]


def test_diagnostic_api_mode_records_incomplete_run(monkeypatch):
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "test-operator-token")
    monkeypatch.setattr("backend.main.create_app", create_app)
    from backend.cli.smoke_assessment import run_cases
    adapter, _ = provider_for([httpx.Response(503)])
    monkeypatch.setattr("backend.pipelines.assessment.pipeline.Provider", lambda settings: adapter)
    record, code = asyncio.run(run_cases(config(), {"D01"}, use_api=True))
    assert code == 1 and record["transport"] == "asgi_api"
    saved = record["cases"][0]
    assert saved["http_status"] == 503 and saved["outcome"] == "incomplete"
    assert saved["result"]["run_status"] == "incomplete" and saved["result"]["assessment"] is None
    assert saved["stage_outcomes"] == {"extraction": "failed"}


def test_tampered_requirements_fail_final_provenance_check():
    adapter, _ = provider_for([draft()])
    result = asyncio.run(synthesize_assessment(powder(), ledger(), provider=adapter))
    result.requirements.stated[0].input_quote = "invented quote"
    with pytest.raises(AssessmentValidationError) as error:
        validate_final(result, powder(), ledger())
    assert any("customer provenance mismatch" in x for x in error.value.errors)


def test_shared_customer_constraints_remain_in_go_no_go_criteria():
    text = "powder moisture. Both streams must respond within 2 seconds."
    facts = facts_for(text, {"context_id": "stream_1", "label": "powder", "sample_phase": "powder",
                            "target_analytes": ["moisture"]},
                      shared=["Both streams must respond within 2 seconds."])
    adapter, _ = provider_for([draft()])
    result = asyncio.run(synthesize_assessment(facts, ledger(), provider=adapter))
    assert "Both streams must respond within 2 seconds." in result.experiment.decision_criteria
    assert "/shared_constraints/0" in result.experiment.decision_criteria
    for metric in ("error", "bias", "response time", "robustness"):
        assert metric in result.experiment.decision_criteria


def test_customer_summary_cannot_import_source_equipment_details():
    data = draft()
    data["case_summary"] = "The customer uses a rotary press with an exact instrument."
    adapter, _ = provider_for([data])
    result = asyncio.run(synthesize_assessment(powder(), ledger(), provider=adapter))
    assert "rotary" not in result.case_summary and "exact instrument" not in result.case_summary
    assert "powder" in result.case_summary and "moisture" in result.case_summary
    result.case_summary = "invented customer detail"
    with pytest.raises(AssessmentValidationError) as error:
        validate_final(result, powder(), ledger())
    assert any("/case_summary" in x for x in error.value.errors)
