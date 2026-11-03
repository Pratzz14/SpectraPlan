import asyncio
import copy
import json
import time
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from backend.pipelines.assessment.pipeline import (
    EXTRACTION_PROMPT, EXTRACTION_PROMPT_VERSION, ExtractionOutput,
    ExtractionValidationError, extract_case, validate_extraction,
)
from backend.core.config import Settings
from backend.main import create_app
from backend.schemas.models import CaseFacts, CustomerStatement, ExtractionRequest, FactProvenance, MeasurementContext
from backend.providers.provider import Provider, ProviderError

DEVELOPMENT = json.loads((Path(__file__).resolve().parents[1] / "evaluation/development.json").read_text(encoding="utf-8"))["cases"]
MULTI = "Stream A is a powder with API. Stream B is opaque milk; measure fat and protein. Both streams must retain laboratory checks."
CLAIM = "We own a fluorescence instrument. We believe it measures protein accurately in milk. We want to measure protein."


def config(**kwargs):
    return Settings(_env_file=None, **{"provider_name": "groq", "groq_api_key": "test-secret", "provider_max_retries": 0, **kwargs})


def facts_for(description, *contexts, shared=(), statements=()):
    """Build explicit fixture responses; the model does not generate these in unit tests."""
    facts = CaseFacts(contexts=[MeasurementContext(**c) for c in contexts], shared_constraints=list(shared),
                      customer_claims_and_requests=[CustomerStatement(**s) for s in statements])
    for i, context in enumerate(facts.contexts):
        for name, value in context.model_dump().items():
            if name in {"context_id", "missing_information"} or value is None:
                continue
            values = [(f"/contexts/{i}/{name}/{j}", item) for j, item in enumerate(value)] if isinstance(value, list) else [(f"/contexts/{i}/{name}", value)]
            for path, _ in values:
                facts.fact_provenance.append(FactProvenance(field_path=path, context_ids=[context.context_id], input_quote=description))
    for i, _ in enumerate(shared):
        facts.fact_provenance.append(FactProvenance(field_path=f"/shared_constraints/{i}", context_ids=[], input_quote=description))
    return facts


def powder(description="A powder; measure moisture."):
    return facts_for(description, {"context_id": "stream_1", "label": "powder", "sample_phase": "powder", "target_analytes": ["moisture"], "missing_information": ["Concentration range", "Required error", "Response time"]})


def wire_for(data):
    """Fixture encoder for the quoted provider contract, independent of its decoder."""
    quotes = {p["field_path"]: p["input_quote"] for p in data["fact_provenance"]}
    contexts = []
    for i, context in enumerate(data["contexts"]):
        wire = {}
        for name, value in context.items():
            path = f"/contexts/{i}/{name}"
            if name in {"context_id", "missing_information"} or value is None:
                wire[name] = value
            elif isinstance(value, list):
                wire[name] = [{"value": item, "input_quote": quotes.get(f"{path}/{j}", "")} for j, item in enumerate(value)]
            else:
                wire[name] = {"value": value, "input_quote": quotes.get(path, "")}
        contexts.append(wire)
    return {"contexts": contexts, "customer_claims_and_requests": data["customer_claims_and_requests"],
            "shared_constraints": [{"value": value, "input_quote": quotes.get(f"/shared_constraints/{i}", "")} for i, value in enumerate(data["shared_constraints"])],
            "missing_information": data["missing_information"]}


def invoke(description, responses):
    calls = []
    responses = iter(responses)

    def handle(request):
        payload = json.loads(request.content)
        calls.append(payload)
        item = next(responses)
        if isinstance(item, httpx.Response):
            return item
        if isinstance(item, dict) and "fact_provenance" in item:
            item = wire_for(item)
        content = item if isinstance(item, str) else json.dumps(item)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}]})

    adapter = Provider(config(), transport=httpx.MockTransport(handle))
    result = asyncio.run(extract_case(description, provider=adapter))
    return result, calls


def test_safe_defaults_and_strict_models():
    one, two = CaseFacts(), CaseFacts()
    one.shared_constraints.append("one")
    assert two.shared_constraints == []
    a = MeasurementContext(context_id="stream_1", label="a")
    b = MeasurementContext(context_id="stream_2", label="b")
    a.target_analytes.append("API")
    assert b.target_analytes == [] and b.temperature is None and b.response_time_s is None
    for data in [{"verified_capability": True}, {"contexts": "powder"}]:
        with pytest.raises(ValidationError):
            CaseFacts.model_validate(data)
    for text in ["", "  ", "x" * 20001]:
        with pytest.raises(ValidationError):
            ExtractionRequest(description=text)
    assert ExtractionRequest(description="  powder \n").description == "  powder \n"


def test_provider_schema_requires_nested_properties_and_local_defaults_do_not_mask_omission():
    schema = ExtractionOutput.model_json_schema()

    def visit(node):
        if isinstance(node, dict):
            assert "default" not in node
            if "properties" in node:
                assert set(node["required"]) == set(node["properties"])
                assert node["additionalProperties"] is False
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)
    data = wire_for(powder().model_dump())
    del data["contexts"][0]["temperature"]
    with pytest.raises(ValidationError, match="temperature"):
        ExtractionOutput.model_validate(data)
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate({})


@pytest.mark.parametrize("case", [case for case in DEVELOPMENT if case["case_id"] in {"D01", "D02"}], ids=lambda c: c["case_id"])
def test_d01_d02_pipeline_contract(case):
    description = case["description"]
    if case["case_id"] == "D01":
        context = {"context_id": "stream_1", "label": "powder blend", "sample_matrix": "active pharmaceutical ingredient and excipients", "sample_phase": "powder", "target_analytes": ["API"], "measurement_goals": ["follow API concentration changes"], "process_constraints": ["feed frame"], "reference_assays": ["Laboratory checks"]}
    else:
        context = {"context_id": "stream_1", "label": "concentrated milk product", "sample_matrix": "concentrated milk product", "appearance": "opaque", "target_analytes": ["fat", "protein"], "temperature": "vary during production", "process_constraints": ["flows through a processing line", "texture vary during production"], "reference_assays": ["fat and protein analysis"]}
    context["missing_information"] = ["Concentration range", "Required error", "Response time", "Reference assay uncertainty"]
    facts = facts_for(description, context)
    result, calls = invoke(description, [facts.model_dump()])
    assert result == facts and len(result.contexts) == 1
    assert result.contexts[0].concentration_range is None
    assert result.contexts[0].required_error is None
    assert result.contexts[0].response_time_s is None
    assert result.contexts[0].pressure is None
    if case["case_id"] == "D01":
        assert result.contexts[0].sample_phase == "powder"
    else:
        assert result.contexts[0].target_analytes == ["fat", "protein"]
        assert result.contexts[0].sample_phase is None  # Liquid is not explicitly stated.
    assert json.loads(calls[0]["messages"][1]["content"])["description"] == description
    assert calls[0]["messages"][0]["content"] == EXTRACTION_PROMPT
    assert calls[0]["max_completion_tokens"] == 3072
    assert EXTRACTION_PROMPT_VERSION in EXTRACTION_PROMPT


def test_multiple_streams_and_shared_constraints():
    facts = facts_for(MULTI,
                      {"context_id": "stream_1", "label": "Stream A", "sample_phase": "powder", "target_analytes": ["API"]},
                      {"context_id": "stream_2", "label": "Stream B", "sample_matrix": "milk", "appearance": "opaque", "target_analytes": ["fat", "protein"]},
                      shared=["Both streams must retain laboratory checks."])
    result, _ = invoke(MULTI, [facts.model_dump()])
    assert result.contexts[0].appearance is None
    assert result.contexts[1].sample_phase is None
    assert all(c.process_constraints == [] for c in result.contexts)
    assert result.shared_constraints == ["Both streams must retain laboratory checks."]


def test_instrument_claim_is_attributed_and_not_a_verified_capability():
    statements = [
        {"text": "Owns a fluorescence instrument", "kind": "reported_fact", "context_ids": [], "input_quote": "We own a fluorescence instrument."},
        {"text": "Believes fluorescence measures protein accurately", "kind": "customer_claim", "context_ids": ["stream_1"], "input_quote": "We believe it measures protein accurately in milk."},
        {"text": "Measure protein", "kind": "requested_outcome", "context_ids": ["stream_1"], "input_quote": "We want to measure protein."},
        {"text": "Try fluorescence", "kind": "proposed_approach", "context_ids": ["stream_1"], "input_quote": "We want to try fluorescence."},
    ]
    text = CLAIM + " We want to try fluorescence."
    facts = facts_for(text, {"context_id": "stream_1", "label": "milk", "sample_matrix": "milk", "target_analytes": ["protein"]}, statements=statements)
    result, _ = invoke(text, [facts.model_dump()])
    assert {s.kind for s in result.customer_claims_and_requests} == {"reported_fact", "customer_claim", "requested_outcome", "proposed_approach"}
    assert result.contexts[0].required_error is None
    assert result.contexts[0].process_constraints == []


@pytest.mark.parametrize("raw,seconds", [(None, None), ("2 seconds", 2.0), ("1-2 s", None), ("2 min", None), ("2", None), ("under 2 seconds", None)])
def test_missing_or_ambiguous_time_is_not_converted(raw, seconds):
    description = "A liquid. " + (f"Response time {raw}." if raw else "Need earlier results.")
    facts = facts_for(description, {"context_id": "stream_1", "label": "liquid", "sample_phase": "liquid", "response_time_raw": raw, "response_time_s": seconds})
    result, _ = invoke(description, [facts.model_dump()])
    assert result.contexts[0].response_time_s == seconds
    assert result.contexts[0].temperature is None


@pytest.mark.parametrize("raw,seconds", [(None, 0.0), ("2 min", 120.0), ("under 2 seconds", 2.0), ("2 seconds", 3.0)])
def test_unsupported_numeric_response_time_is_rejected(raw, seconds):
    description = "A liquid. " + (raw or "Missing time")
    facts = facts_for(description, {"context_id": "stream_1", "label": "liquid", "response_time_raw": raw, "response_time_s": seconds})
    with pytest.raises(ExtractionValidationError, match="exact raw seconds"):
        validate_extraction(facts, description)


def test_raw_units_ranges_and_pressure_basis():
    text = "A slurry at 20-40 C, 2 bar(g); concentration 5-10% (basis unknown); required error 1 point."
    facts = facts_for(text, {"context_id": "stream_1", "label": "slurry", "sample_phase": "slurry", "temperature": "20-40 C", "pressure": "2 bar(g)", "concentration_range": "5-10% (basis unknown)", "required_error": "1 point", "missing_information": ["What concentration basis?", "Which error basis?"]})
    result, _ = invoke(text, [facts.model_dump()])
    assert result.contexts[0].pressure == "2 bar(g)"
    assert result.contexts[0].concentration_range == "5-10% (basis unknown)"
    facts.contexts[0].temperature = "293.15-313.15 K"
    with pytest.raises(ExtractionValidationError, match="verbatim"):
        validate_extraction(facts, text)


def test_whitespace_wrapped_quotes_are_accepted_but_changed_words_are_rejected():
    text = "A powder;\nmeasure moisture."
    facts = powder(text)
    for record in facts.fact_provenance:
        record.input_quote = "A powder; measure moisture."
    validate_extraction(facts, text)
    facts.fact_provenance[0].input_quote = "A powder; measure contaminants."
    with pytest.raises(ExtractionValidationError, match="exact substring"):
        validate_extraction(facts, text)


def test_field_recovery_preserves_original_constraints_and_omits_bad_quotes():
    from backend.pipelines.assessment.pipeline import ExtractionOutput, recover_extraction_fields
    text = "A powder; measure moisture. Do not exceed 40 C or reuse the cable."
    data = wire_for(powder(text).model_dump())
    quote = "Do not exceed 40 C or reuse the cable."
    data["shared_constraints"] = [
        {"value": "Reuse the cable at 50 C", "input_quote": quote},
        {"value": "invented fact", "input_quote": "No such source sentence"},
    ]
    recovered, warnings = recover_extraction_fields(ExtractionOutput.model_validate(data), text)
    assert len(recovered.shared_constraints) == 1
    assert recovered.shared_constraints[0].value == quote
    assert recovered.shared_constraints[0].input_quote == quote
    assert len(warnings) == 2
    assert all(warning in recovered.missing_information for warning in warnings)
    validate_extraction(recovered.to_facts(text), text)


def test_generalized_sample_form_and_shared_constraint_duplication_are_rejected():
    facts = powder()
    facts.contexts[0].sample_phase = "solid"
    with pytest.raises(ExtractionValidationError, match="do not infer or generalize"):
        validate_extraction(facts, "A powder; measure moisture.")
    facts.contexts[0].sample_phase = None
    with pytest.raises(ExtractionValidationError, match="extract that exact form"):
        validate_extraction(facts, "A powder; measure moisture.")
    text = "Stream A and Stream B both need laboratory checks."
    facts = facts_for(text,
                      {"context_id": "stream_1", "label": "Stream A", "reference_assays": ["laboratory checks"]},
                      {"context_id": "stream_2", "label": "Stream B", "reference_assays": ["laboratory checks"]})
    with pytest.raises(ExtractionValidationError, match="shared constraint once"):
        validate_extraction(facts, text)


def test_separately_scoped_constraints_and_required_item_quotes():
    text = "Stream A uses laboratory checks. Stream B uses laboratory checks."
    facts = facts_for(text,
                      {"context_id": "stream_1", "label": "Stream A", "reference_assays": ["laboratory checks"]},
                      {"context_id": "stream_2", "label": "Stream B", "reference_assays": ["laboratory checks"]})
    for record in facts.fact_provenance:
        if "reference_assays" in record.field_path:
            record.input_quote = "Stream A uses laboratory checks." if record.context_ids == ["stream_1"] else "Stream B uses laboratory checks."
    validate_extraction(facts, text)
    wire = wire_for(facts.model_dump())
    del wire["contexts"][0]["reference_assays"][0]["input_quote"]
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate(wire)


@pytest.mark.parametrize("mutation,match", [
    (lambda f: f.fact_provenance.pop(), "missing fact provenance"),
    (lambda f: setattr(f.fact_provenance[0], "input_quote", "Invented sentence"), "exact substring"),
    (lambda f: setattr(f.fact_provenance[0], "field_path", "/contexts/0/nonexistent"), "does not reference"),
    (lambda f: setattr(f.fact_provenance[0], "context_ids", ["stream_2"]), "do not match"),
    (lambda f: f.contexts.append(copy.deepcopy(f.contexts[0])), "unique"),
    (lambda f: f.customer_claims_and_requests.append(CustomerStatement(text="bad", kind="customer_claim", context_ids=["stream_9"], input_quote="powder")), "invalid context_ids"),
    (lambda f: f.customer_claims_and_requests.append(CustomerStatement(text="bad", kind="customer_claim", input_quote="not in input")), "exact substring"),
])
def test_invalid_provenance_and_contexts(mutation, match):
    facts = powder()
    mutation(facts)
    with pytest.raises(ExtractionValidationError, match=match):
        validate_extraction(facts, "A powder; measure moisture.")


def test_repair_uses_errors_and_original_input():
    facts = powder()
    invalid = facts.model_dump()
    invalid["fact_provenance"][0]["input_quote"] = "Invented quote"
    result, calls = invoke("A powder; measure moisture.", [invalid, facts.model_dump()])
    assert result == facts and len(calls) == 2
    feedback = json.loads(calls[1]["messages"][-1]["content"])
    assert any("exact substring" in e for e in feedback["validation_errors"])
    assert calls[0]["messages"][:2] == calls[1]["messages"][:2]


def test_stage_respects_lower_global_output_ceiling():
    class FakeProvider:
        settings = config(provider_max_completion_tokens=256, extraction_max_completion_tokens=1024)

        async def structured(self, messages, response_model, **kwargs):
            assert kwargs["max_completion_tokens"] == 256
            return ExtractionOutput.model_validate(wire_for(powder().model_dump()))

    assert asyncio.run(extract_case("A powder; measure moisture.", provider=FakeProvider())) == powder()


@pytest.mark.parametrize("invalid", ["not JSON", {}, {"contexts": []}, {"contexts": "wrong"}])
def test_schema_repair_is_bounded(invalid):
    with pytest.raises(ProviderError) as caught:
        invoke("A powder; measure moisture.", [invalid, invalid])
    assert caught.value.code == "extraction_invalid_response" and caught.value.http_status == 502


def test_schema_repair_success():
    facts = powder()
    result, calls = invoke("A powder; measure moisture.", [{}, facts.model_dump()])
    assert result == facts and len(calls) == 2


def test_provider_generated_json_rejection_uses_one_repair():
    facts = powder()
    rejection = httpx.Response(400, json={"error": {"code": "json_validate_failed"}})
    result, calls = invoke("A powder; measure moisture.", [rejection, facts.model_dump()])
    assert result == facts and len(calls) == 2
    with pytest.raises(ProviderError) as caught:
        invoke("A powder; measure moisture.", [rejection, rejection])
    assert caught.value.code == "extraction_invalid_response"


def test_provider_failure_is_not_repaired():
    with pytest.raises(ProviderError) as caught:
        invoke("A powder", [httpx.Response(401, json={"error": "private-details"})])
    assert caught.value.code == "provider_authentication"
    assert "private-details" not in str(caught.value)


def test_repair_shares_deadline_and_expired_deadline_does_not_call():
    class FakeProvider:
        settings = config()
        calls = []

        async def structured(self, messages, response_model, **kwargs):
            self.calls.append(kwargs["deadline"])
            if len(self.calls) == 1:
                raise ProviderError("provider_invalid_response", "invalid", 502)
            return ExtractionOutput.model_validate(wire_for(powder().model_dump()))

    adapter = FakeProvider()
    stop = time.monotonic() + 20
    asyncio.run(extract_case("A powder; measure moisture.", provider=adapter, deadline=stop))
    assert adapter.calls == [stop, stop]
    with pytest.raises(ProviderError) as caught:
        asyncio.run(extract_case("A powder", provider=adapter, deadline=time.monotonic() - 1))
    assert caught.value.code == "provider_timeout" and len(adapter.calls) == 2


def api_request(payload, settings=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings or config())), base_url="http://test") as client:
            return await client.post("/api/extract", json=payload)
    return asyncio.run(run())


@pytest.mark.parametrize("body", [{}, {"description": " "}, {"description": "x" * 20001}, {"description": 7}, {"description": "a", "extra": True}])
def test_api_rejects_invalid_requests(body, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Invalid input must not call the provider")
    monkeypatch.setattr("backend.api.routers.assessment.extract_case", forbidden)
    assert api_request(body).status_code == 422


def test_api_validated_output_is_independent_of_corpus(tmp_path, monkeypatch):
    async def fake(description, settings):
        assert description == "A powder; measure moisture."
        return powder()
    monkeypatch.setattr("backend.api.routers.assessment.extract_case", fake)
    response = api_request({"description": "A powder; measure moisture."}, config(corpus_dir=tmp_path / "absent"))
    assert response.status_code == 200
    assert response.json()["contexts"][0]["sample_phase"] == "powder"
    assert response.json()["fact_provenance"]


@pytest.mark.parametrize("code,status", [("provider_not_configured", 503), ("provider_timeout", 504), ("extraction_invalid_response", 502)])
def test_api_failure_contract(code, status, monkeypatch):
    async def fail(*args, **kwargs):
        raise ProviderError(code, "Sanitized failure", status)
    monkeypatch.setattr("backend.api.routers.assessment.extract_case", fail)
    response = api_request({"description": "A liquid"})
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code, "message": "Sanitized failure"}}


def test_api_actual_unconfigured_provider():
    response = api_request({"description": "A liquid"}, Settings(_env_file=None, groq_api_key=""))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_not_configured"


def test_smoke_record_preserves_failures_and_prompt_metadata(monkeypatch):
    from backend.cli.smoke_extraction import run_cases

    async def fake(description, settings, **kwargs):
        if description.startswith("We manufacture"):
            raise ProviderError("provider_timeout", "Provider request deadline expired.", 504)
        return CaseFacts(missing_information=["Please describe your sample"])

    monkeypatch.setattr("backend.cli.smoke_extraction.extract_case", fake)
    record, code = asyncio.run(run_cases(config(), {"D01", "D02"}))
    assert code == 1
    assert record["prompt_version"] == EXTRACTION_PROMPT_VERSION
    assert len(record["prompt_sha256"]) == 64
    assert record["review_status"] == "pending_manual_semantic_review"
    assert record["cases"][0]["facts"] is None
    assert record["cases"][0]["error"]["code"] == "provider_timeout"
    assert record["cases"][1]["outcome"] == "passed_mechanical_validation"
    assert "test-secret" not in json.dumps(record)


def test_failed_repair_diagnostics_stay_out_of_api(monkeypatch):
    async def fail(*args, **kwargs):
        error = ProviderError("extraction_invalid_response", "Extraction failed validation.", 502)
        error.invalid_content = "private malformed model content"
        error.validation_errors = ["internal diagnostic"]
        raise error

    monkeypatch.setattr("backend.api.routers.assessment.extract_case", fail)
    response = api_request({"description": "A liquid"})
    assert response.status_code == 502
    assert "private" not in response.text and "internal diagnostic" not in response.text
