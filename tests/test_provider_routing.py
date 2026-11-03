"""Synthetic probes and payloads; no live credentials or external traffic."""
import asyncio
import json
import time

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from backend.core.config import Settings
from backend.main import create_app
from backend.providers.provider import Provider, ProviderError
from backend.cli.provider_setup import with_public_trial


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str


def config(**values):
    return Settings(_env_file=None, **{"provider_name": "auto", "groq_api_key": "fake-groq",
        "llmtech_api_key": "fake-llmtech", **values})


def response(payload):
    return httpx.Response(200, json={"model": "returned-model", "choices": [
        {"finish_reason": "stop", "message": {"content": json.dumps(payload)}}]})


def call(adapter, **kwargs):
    return adapter.structured([{"role": "user", "content": "synthetic payload"}], Output, **kwargs)


def test_profiles_have_matching_models_endpoints_and_placeholder_keys():
    settings = config(provider_model="old-groq-only-model", provider_base_url="https://old.example/v1")
    llmtech, groq = settings.for_provider("llmtech"), settings.for_provider("groq")
    assert llmtech.provider_base_url == "https://api.llmtech.eu/v1"
    assert llmtech.provider_model == "nvidia/Qwen3.8-27B-NVFP4"
    assert groq.provider_base_url == "https://api.groq.com/openai/v1"
    assert groq.provider_model == "qwen/qwen3.8-27b"
    assert not config(groq_api_key="your_groq_api_key_here", llmtech_api_key="your_key_here").provider_configured
    assert config(provider_name="llmtech").provider_model == llmtech.provider_model
    with pytest.raises(ValidationError):
        config(provider_order="groq,groq")


def test_selects_preferred_and_caches_probe_across_requests():
    settings, calls = config(), []
    def handle(request):
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer fake-llmtech"
        assert "groq" not in str(request.url)
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        probe = body["response_format"]["json_schema"]["name"] == "AvailabilityProbe"
        calls.append("probe" if probe else "payload")
        return response({"ok": True} if probe else {"answer": "done"})
    async def run():
        for _ in range(2):
            adapter = Provider(settings, transport=httpx.MockTransport(handle))
            assert (await call(adapter)).answer == "done"
            assert adapter.identity()["provider"] == "llmtech"
    asyncio.run(run())
    assert calls == ["probe", "payload", "payload"]


@pytest.mark.parametrize("failure", [401, 402, 429, 503, "timeout", "invalid_probe"])
def test_unavailable_preferred_provider_selects_other_without_sending_payload(failure):
    calls = []
    def handle(request):
        body = json.loads(request.content)
        llmtech = request.url.host == "api.llmtech.eu"
        calls.append((llmtech, body["messages"]))
        if llmtech:
            if failure == "timeout":
                raise httpx.ReadTimeout("private detail")
            return response({"ok": False}) if failure == "invalid_probe" else httpx.Response(failure)
        assert request.headers["authorization"] == "Bearer fake-groq"
        assert body["model"] == "qwen/qwen3.8-27b" and "chat_template_kwargs" not in body
        return response({"ok": True} if len(calls) == 2 else {"answer": "done"})
    adapter = Provider(config(), transport=httpx.MockTransport(handle))
    assert asyncio.run(call(adapter)).answer == "done"
    assert adapter.current_settings.provider_name == "groq" and len(calls) == 3
    assert "synthetic payload" not in json.dumps(calls[0])
    assert adapter.attempts[0]["outcome"] == "failed"


@pytest.mark.parametrize("failure", [401, 402, 429, 503, "timeout", "schema_rejected"])
def test_payload_failure_falls_back_once_per_provider(failure):
    calls = []
    def handle(request):
        body = json.loads(request.content)
        probe = body["response_format"]["json_schema"]["name"] == "AvailabilityProbe"
        calls.append((request.url.host, probe))
        if probe:
            return response({"ok": True})
        if request.url.host == "api.llmtech.eu":
            if failure == "timeout":
                raise httpx.ReadTimeout("private detail")
            if failure == "schema_rejected":
                return httpx.Response(400, json={"error": {"code": "schema_validation_error"}})
            return httpx.Response(failure)
        return response({"answer": "fallback"})
    adapter = Provider(config(), transport=httpx.MockTransport(handle))
    assert asyncio.run(call(adapter)).answer == "fallback"
    assert calls == [("api.llmtech.eu", True), ("api.llmtech.eu", False),
                     ("api.groq.com", True), ("api.groq.com", False)]
    assert adapter.identity()["provider"] == "groq"


@pytest.mark.parametrize("rejection", [False, True])
def test_bad_model_content_stays_on_existing_repair_path(rejection):
    calls = []
    def handle(request):
        body = json.loads(request.content)
        calls.append(request.url.host)
        if body["response_format"]["json_schema"]["name"] == "AvailabilityProbe":
            return response({"ok": True})
        return (httpx.Response(400, json={"error": {"code": "json_validate_failed"}})
                if rejection else response({"wrong": "schema"}))
    adapter = Provider(config(), transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderError) as error:
        asyncio.run(call(adapter))
    assert error.value.code in {"provider_invalid_response", "provider_request_rejected"}
    assert calls == ["api.llmtech.eu", "api.llmtech.eu"]


def test_all_unavailable_is_bounded_cached_and_secret_free():
    settings, calls = config(), []
    def handle(request):
        calls.append(request)
        return httpx.Response(401, text="private fake-groq fake-llmtech")
    async def run():
        for _ in range(2):
            adapter = Provider(settings, transport=httpx.MockTransport(handle))
            with pytest.raises(ProviderError) as error:
                await call(adapter)
            assert error.value.code == "provider_unavailable"
            assert "private" not in str(error.value)
    asyncio.run(run())
    assert len(calls) == 2


def test_expired_deadline_does_not_call_any_provider():
    adapter = Provider(config(), transport=httpx.MockTransport(lambda r: pytest.fail("unexpected network")))
    with pytest.raises(ProviderError) as error:
        asyncio.run(call(adapter, deadline=time.monotonic() - 1))
    assert error.value.http_status == 504


def test_all_probe_timeouts_keep_timeout_http_mapping():
    def timeout(request):
        raise httpx.ReadTimeout("private detail")
    adapter = Provider(config(), transport=httpx.MockTransport(timeout))
    with pytest.raises(ProviderError) as error:
        asyncio.run(call(adapter))
    assert error.value.http_status == 504 and len(adapter.attempts) == 2


def test_slow_probe_and_payload_share_deadline():
    calls = []
    async def handle(request):
        calls.append(request)
        await asyncio.sleep(1)
        return response({"ok": True})
    adapter = Provider(config(provider_probe_timeout_s=.02), transport=httpx.MockTransport(handle))
    async def run():
        start = time.monotonic()
        with pytest.raises(ProviderError) as error:
            await call(adapter, deadline=start + .03)
        assert error.value.http_status == 504 and time.monotonic() - start < .5
    asyncio.run(run())
    assert len(calls) <= 2 and all(a["outcome"] == "failed" for a in adapter.attempts)


def test_single_flight_probe_for_concurrent_requests():
    settings, probes = config(), []
    async def handle(request):
        if json.loads(request.content)["response_format"]["json_schema"]["name"] == "AvailabilityProbe":
            probes.append(True)
            await asyncio.sleep(.02)
            return response({"ok": True})
        return response({"answer": "done"})
    async def run():
        return await asyncio.gather(*(call(Provider(settings, transport=httpx.MockTransport(handle))) for _ in range(3)))
    assert len(asyncio.run(run())) == 3 and len(probes) == 1


def test_cache_expiry_rechecks_and_mode_can_be_pinned():
    settings = config(provider_order="groq,llmtech")
    calls = []
    def handle(request):
        calls.append(request.url.host)
        body = json.loads(request.content)
        return response({"ok": True} if body["response_format"]["json_schema"]["name"] == "AvailabilityProbe" else {"answer": "done"})
    adapter = Provider(settings, transport=httpx.MockTransport(handle))
    asyncio.run(call(adapter))
    settings._provider_router.states["groq"]["expires_at"] = 0
    asyncio.run(call(adapter))
    assert calls == ["api.groq.com"] * 4
    pinned = Provider(settings.for_provider("llmtech"), transport=httpx.MockTransport(handle))
    asyncio.run(call(pinned))
    assert len(pinned.attempts) == 0 and calls[-1] == "api.llmtech.eu"


def test_lifespan_checks_automatically_and_health_only_reads_cache(tmp_path, monkeypatch):
    settings = config(corpus_dir=tmp_path)
    calls = []
    def handle(request):
        calls.append(True)
        return response({"ok": True})
    real = Provider
    monkeypatch.setattr("backend.main.Provider", lambda config: real(config, transport=httpx.MockTransport(handle)))
    settings.provider_probe_on_startup = True
    app = create_app(settings)
    async def run():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                for _ in range(2):
                    health = (await client.get("/api/health")).json()
                    assert health["provider"]["selected"] == "llmtech"
                    assert next(p for p in health["provider"]["candidates"] if p["name"] == "llmtech")["status"] == "working"
    asyncio.run(run())
    assert len(calls) == 1


def test_public_trial_never_replaces_an_existing_key(monkeypatch):
    monkeypatch.setattr("backend.cli.provider_setup.httpx.get", lambda *a, **k: pytest.fail("unexpected lookup"))
    settings = config()
    assert with_public_trial(settings) is settings


def test_pdf_ingestion_identity_is_independent_of_assessment_providers():
    from backend.pipelines.pdf_knowledge.extract import pipeline_fingerprint
    first = pipeline_fingerprint(config())
    second = pipeline_fingerprint(config(groq_model="different-model"))
    assert first == second and first["model"] == "qwen3.7-flash"


def test_assessment_records_provider_switch_between_stages(monkeypatch):
    from backend.pipelines.assessment.pipeline import assess_case
    from tests.test_assessment import DESCRIPTION, draft, ledger
    from tests.test_extraction import powder, wire_for
    monkeypatch.setattr("backend.pipelines.assessment.pipeline.authenticate_ledger", lambda *args: None)
    class Retrieval:
        def retrieve_case(self, facts, deadline):
            return ledger()
    sent = []
    def handle(request):
        body = json.loads(request.content)
        name = body["response_format"]["json_schema"]["name"]
        if name == "AvailabilityProbe":
            return response({"ok": True})
        if name == "ExtractionOutput":
            return response(wire_for(powder().model_dump()))
        sent.append(body["messages"])
        return httpx.Response(503) if request.url.host == "api.llmtech.eu" else response(draft())
    adapter = Provider(config(), transport=httpx.MockTransport(handle))
    result = asyncio.run(assess_case(DESCRIPTION, provider=adapter, retrieval_service=Retrieval()))
    assert result.run_status == "complete" and result.metadata.provider_mode == "auto"
    assert result.metadata.stage_providers["extraction"]["provider"] == "llmtech"
    assert result.metadata.stage_providers["synthesis"]["provider"] == "groq"
    assert result.metadata.provider == "groq" and sent[0] == sent[1]
    assert any(a["purpose"] == "request" and a["outcome"] == "failed" for a in result.metadata.provider_attempts)
