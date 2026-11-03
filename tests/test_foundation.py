import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from backend.core.config import PROJECT_ROOT, Settings
from backend.services.health import inspect_corpus
from backend.main import create_app
from backend.providers.provider import Provider, ProviderError, _retry_delay
from backend.cli.smoke_provider import run_smoke
from tests.corpus_fixture import make_corpus


def settings(**overrides):
    return Settings(_env_file=None, **{"provider_name": "groq", "groq_api_key": "test-secret", **overrides})


def health_response(config):
    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(config)), base_url="http://test"
        ) as client:
            return await client.get("/api/health")

    return asyncio.run(request())


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sample_phase: str
    target: str


def completion(content=None, *, finish="stop", message=None):
    return {"choices": [{"finish_reason": finish, "message": message if message is not None else {
        "content": content if content is not None else '{"sample_phase":"powder","target":"moisture"}'
    }}]}


def invoke(handler, **options):
    return asyncio.run(Provider(settings(**options), transport=httpx.MockTransport(handler)).structured(
        [{"role": "user", "content": "A powder; measure moisture."}], Extraction
    ))


def write_corpus(directory: Path, *, approved=True, revision="corpus-v1"):
    make_corpus(directory, eligible=approved, revision=revision)


def test_configuration_env_precedence_and_paths(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=file-secret\nPROVIDER_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "env-secret")
    monkeypatch.chdir(tmp_path)
    config = Settings(_env_file=env_file, corpus_dir="knowledge", provider_name="groq")
    assert config.groq_api_key.get_secret_value() == "env-secret"
    assert config.provider_model == "file-model"
    assert config.corpus_dir == PROJECT_ROOT / "knowledge"
    assert "env-secret" not in repr(config)


@pytest.mark.parametrize("key", ["", "  ", "your_groq_api_key_here", "replace_me"])
def test_missing_and_placeholder_keys(key):
    assert not settings(groq_api_key=key).provider_configured


@pytest.mark.parametrize("values", [
    {"provider_call_timeout_s": 0}, {"request_deadline_s": -1},
    {"provider_max_retries": 3}, {"provider_model": " "},
    {"provider_base_url": "https://secret@example.com"},
])
def test_invalid_settings(values):
    with pytest.raises(ValidationError):
        settings(**values)


def test_health_is_free_and_secret_free(tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Health must not call the provider")

    monkeypatch.setattr(Provider, "structured", forbidden)
    response = health_response(settings(corpus_dir=tmp_path))
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "running" and not data["ready"]
    assert data["provider"]["configured"]
    assert data["corpus"] == {"status": "missing", "version": None, "eligible_passages": 0, "eligible_methods": 0,
                              "flagged_records": 0, "human_verified_records": 0}
    assert "test-secret" not in response.text and str(tmp_path) not in response.text


def test_health_requires_provider_and_corpus(tmp_path):
    write_corpus(tmp_path)
    for key, ready in [("", False), ("test-secret", True)]:
        data = health_response(settings(corpus_dir=tmp_path, groq_api_key=key)).json()
        assert data["ready"] is ready
        assert data["corpus"]["version"] == "corpus-v1"
        assert data["corpus"]["eligible_passages"] == 1
        assert data["corpus"]["eligible_methods"] == 19


def test_corpus_excluded_membership_and_independent_content_revision(tmp_path):
    write_corpus(tmp_path, approved=False)
    assert inspect_corpus(tmp_path).status == "invalid"
    # A record revision is independent of the aggregate corpus version.
    fresh = tmp_path / "fresh"
    write_corpus(fresh, revision="independent-content-revision")
    assert inspect_corpus(fresh).status == "ready"


@pytest.mark.parametrize("filename", ["source_manifest.json", "passages.jsonl", "methods.json"])
def test_corpus_corruption(tmp_path, filename):
    write_corpus(tmp_path)
    (tmp_path / filename).write_text("not JSON", encoding="utf-8")
    assert inspect_corpus(tmp_path).status == "invalid"


def test_corpus_unreadable(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("private local path")

    monkeypatch.setattr(Path, "read_text", denied)
    assert inspect_corpus(tmp_path).status == "unreadable"


def test_corpus_malformed_record_and_duplicate_id(tmp_path):
    write_corpus(tmp_path)
    passage_file = tmp_path / "passages.jsonl"
    passage_file.write_text(passage_file.read_text() * 2)
    assert inspect_corpus(tmp_path).status == "invalid"
    passage_file.write_text('{"approval_status":"approved"}\n')
    assert inspect_corpus(tmp_path).status == "invalid"


def test_provider_request_and_local_validation():
    def handle(request):
        assert request.url == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-secret"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen/qwen3.8-27b"
        assert payload["reasoning_effort"] == "medium"
        assert payload["reasoning_format"] == "hidden"
        schema = payload["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        return httpx.Response(200, json=completion())

    result = invoke(handle)
    assert result == Extraction(sample_phase="powder", target="moisture")


def test_llmtech_uses_its_own_key_and_request_fields():
    def handle(request):
        assert request.headers["authorization"] == "Bearer llmtech-test-secret"
        payload = json.loads(request.content)
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert "reasoning_format" not in payload and "reasoning_effort" not in payload
        return httpx.Response(200, json=completion())
    assert not settings(provider_name="llmtech").provider_configured
    result = invoke(handle, provider_name="llmtech", llmtech_api_key="llmtech-test-secret")
    assert result.sample_phase == "powder"


def test_llmtech_exhausted_credit_fails_without_retry():
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(402, json={"error": {"message": "private quota details"}})
    with pytest.raises(ProviderError) as caught:
        invoke(handle, provider_name="llmtech", llmtech_api_key="llmtech-test-secret")
    assert caught.value.daily_limit and caught.value.upstream_status == 402
    assert len(calls) == 1 and "private" not in str(caught.value)


@pytest.mark.parametrize("data", [
    {}, [], {"choices": []}, {"choices": ["bad"]},
    completion(message="bad"), completion(message={"content": None}),
    completion("not json"), completion('{"sample_phase":"powder"}'),
    completion('{"sample_phase":123,"target":"moisture"}'),
    completion('{"sample_phase":"powder","target":"moisture","invented":true}'),
    completion(finish="length"), completion(message={"refusal": "no", "content": "{}"}),
])
def test_invalid_provider_results_are_not_retried(data):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=data)

    with pytest.raises(ProviderError) as caught:
        invoke(handle)
    assert caught.value.code == "provider_invalid_response"
    assert caught.value.http_status == 502 and len(calls) == 1


@pytest.mark.parametrize("status,code", [(400, "provider_request_rejected"), (401, "provider_authentication"),
                                          (403, "provider_authentication"), (302, "provider_request_rejected")])
def test_provider_rejections_are_sanitized_and_not_retried(status, code):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, text="test-secret and private upstream details")

    with pytest.raises(ProviderError) as caught:
        invoke(handle)
    assert caught.value.code == code and len(calls) == 1
    assert "test-secret" not in str(caught.value)


@pytest.mark.parametrize("failure", [429, 500, "connection", "timeout"])
def test_transient_retries_are_bounded(failure, monkeypatch):
    monkeypatch.setattr("backend.providers.provider._retry_delay", lambda *_: 0)
    calls = []

    def handle(request):
        calls.append(request)
        if failure == "connection":
            raise httpx.ConnectError("secret upstream", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("secret upstream", request=request)
        return httpx.Response(failure)

    with pytest.raises(ProviderError) as caught:
        invoke(handle)
    assert len(calls) == 3
    assert caught.value.http_status == (504 if failure == "timeout" else 503)
    assert "secret upstream" not in str(caught.value)


def test_retry_can_recover(monkeypatch):
    monkeypatch.setattr("backend.providers.provider._retry_delay", lambda *_: 0)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=completion())

    assert invoke(handle).target == "moisture"
    assert len(calls) == 2


@pytest.mark.parametrize("raw,expected", [("4", 4), ("1000", 10), ("bad", 1), ("NaN", 10)])
def test_retry_after_is_bounded(raw, expected):
    assert _retry_delay(httpx.Response(429, headers={"Retry-After": raw}), 0) == expected


def test_retry_delay_respects_shared_deadline():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "5"})

    started = time.monotonic()
    with pytest.raises(ProviderError) as caught:
        invoke(handle, request_deadline_s=0.05)
    assert caught.value.code == "provider_timeout" and len(calls) == 1
    assert time.monotonic() - started < 1


@pytest.mark.parametrize("limit", ["call", "total"])
def test_actual_wall_clock_deadlines(limit):
    calls = []

    async def handle(request):
        calls.append(request)
        await asyncio.sleep(2)
        return httpx.Response(200, json=completion())

    options = {"provider_max_retries": 0, "provider_call_timeout_s": 0.02} if limit == "call" else {"request_deadline_s": 0.02}
    started = time.monotonic()
    with pytest.raises(ProviderError) as caught:
        invoke(handle, **options)
    assert caught.value.code == "provider_timeout" and len(calls) == 1
    assert time.monotonic() - started < 1


@pytest.mark.parametrize("deadline", [0, -1])
def test_expired_caller_deadline_never_calls_provider(deadline):
    def forbidden(request):
        pytest.fail("Expired request must not call the provider")

    with pytest.raises(ProviderError) as caught:
        asyncio.run(Provider(settings(), transport=httpx.MockTransport(forbidden)).structured(
            [], Extraction, deadline=deadline
        ))
    assert caught.value.code == "provider_timeout"


def test_missing_key_smoke_is_explicit_and_does_not_call(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Missing key must not open HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    record, code = asyncio.run(run_smoke(settings(groq_api_key="")))
    assert code == 1 and record["outcome"] == "unresolved"
    assert record["error"]["code"] == "provider_not_configured"
    assert record["validated_response"] is None
