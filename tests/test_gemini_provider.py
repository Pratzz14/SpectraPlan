"""Gemini native input, validation and Qwen fallback without external calls."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from backend.pipelines.assessment.pipeline import extract_case
from backend.core.config import Settings
from backend.providers.gemini_provider import interaction_payload
from backend.providers.provider import Provider, ProviderError
from tests.test_extraction import powder, wire_for


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str


def config(**values):
    return Settings(_env_file=None, **{"gemini_api_key":"fake-gemini", "llmtech_api_key":"fake-qwen",
        "provider_max_retries":0, **values})


def client_for(create):
    return SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))


def test_native_payload_matches_installed_sdk_and_preserves_image():
    from google.genai._gaos.types.interactions.createmodelinteraction import CreateModelInteraction
    payload = interaction_payload([
        {"role":"system","content":"Use only source evidence."},
        {"role":"user","content":[{"type":"text","text":"Source page"},
          {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,YWJj"}}]}],
        Output.model_json_schema(),config().for_provider("gemini"),1024)
    parsed = CreateModelInteraction.model_validate(payload)
    assert parsed.model == "gemini-3.8-flash"
    assert payload["input"][1] == {"type":"image","mime_type":"image/jpeg","data":"YWJj"}
    assert payload["store"] is False and "temperature" not in payload["generation_config"]


def test_successful_gemini_records_real_stage_usage_and_raw_output():
    async def create(**kwargs):
        probe = "ok" in kwargs["response_format"]["schema"]["properties"]
        return {"steps":[{"type":"model_output","content":[{"type":"text",
                  "text":json.dumps({"ok":True} if probe else {"answer":"done"})}]}],
                "model":"gemini-3.8-flash", "status":"completed",
                "usage":{"total_input_tokens":12,"total_output_tokens":3,"total_tokens":15}}
    adapter = Provider(config(),gemini_client=client_for(create))
    adapter.stage = "synthesis"
    seen = []; adapter.on_event = seen.append
    result = asyncio.run(adapter.structured([{"role":"user","content":"Synthetic"}],Output,temperature=0))
    assert result.answer == "done" and adapter.identity()["provider"] == "gemini"
    assert adapter.last_usage["total_tokens"] == 15
    assert all(e["stage"] == "synthesis" for e in seen)
    assert any(e["payload"].get("raw_content") == '{"answer": "done"}' for e in seen)
    assert "fake-gemini" not in json.dumps(seen)


@pytest.mark.parametrize("failure",[401,429,503,"timeout"])
def test_gemini_failure_uses_qwen_with_matching_credentials(failure):
    async def create(**kwargs):
        if failure == "timeout":
            raise TimeoutError
        error = RuntimeError("private provider message"); error.status_code = failure
        raise error
    def handle(request):
        assert request.url.host == "api.llmtech.eu"
        assert request.headers["authorization"] == "Bearer fake-qwen"
        data = json.loads(request.content)
        probe = data["response_format"]["json_schema"]["name"] == "AvailabilityProbe"
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{
            "content":json.dumps({"ok":True} if probe else {"answer":"fallback"})}}]})
    adapter = Provider(config(),gemini_client=client_for(create),transport=httpx.MockTransport(handle))
    assert asyncio.run(adapter.structured([{"role":"user","content":"Synthetic"}],Output)).answer == "fallback"
    assert adapter.identity()["provider"] == "llmtech"
    assert any(e["event_type"] == "provider_error" for e in adapter.trace_events)


def test_invalid_gemini_output_is_logged_repaired_then_falls_back():
    calls = []
    async def create(**kwargs):
        probe = "ok" in kwargs["response_format"]["schema"]["properties"]
        calls.append(probe)
        return {"output_text":'{"ok":true}' if probe else 'broken JSON',"status":"completed"}
    def handle(request):
        data = json.loads(request.content)
        probe = data["response_format"]["json_schema"]["name"] == "AvailabilityProbe"
        body = {"ok":True} if probe else wire_for(powder().model_dump())
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":json.dumps(body)}}]})
    adapter = Provider(config(),gemini_client=client_for(create),transport=httpx.MockTransport(handle));adapter.stage="extraction"
    result = asyncio.run(extract_case("A powder; measure moisture.",provider=adapter))
    assert result.contexts[0].sample_phase == "powder"
    assert calls == [True,False,False]
    invalid = [e for e in adapter.trace_events if e["payload"].get("raw_content") == "broken JSON"]
    assert len(invalid) == 2 and adapter.identity()["provider"] == "llmtech"


def test_pinned_invalid_gemini_never_silently_accepts_or_switches():
    async def create(**kwargs):
        return {"output_text":"broken JSON", "status":"completed"}
    adapter=Provider(config(provider_name="gemini"),gemini_client=client_for(create))
    with pytest.raises(ProviderError,match="validation"):
        asyncio.run(adapter.structured([{"role":"user","content":"Synthetic"}],Output))
    assert [e["event_type"] for e in adapter.trace_events] == ["provider_request","provider_response","provider_error"]
