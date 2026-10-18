"""Structured provider adapter with one shared deadline and sanitized failures."""

import asyncio
import json
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar, TypedDict

import httpx
from pydantic import BaseModel, ValidationError

from backend.config import Settings

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class Message(TypedDict):
    role: str
    content: str | list[dict]


class ProviderError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 503, *, upstream_status: int | None = None,
                 upstream_code: str | None = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.upstream_status = upstream_status
        self.upstream_code = upstream_code
        self.daily_limit = False


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    delay = float(2**attempt)
    if response is not None and (raw := response.headers.get("retry-after")):
        try:
            delay = float(raw)
        except ValueError:
            try:
                when = parsedate_to_datetime(raw)
                delay = (when - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                pass
    return min(10.0, max(0.0, delay)) if math.isfinite(delay) else 10.0


class Provider:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport
        self.last_usage: dict = {}
        self.last_model: str | None = None
        self.repair_counts: dict[str, int] = {}
        self.current_settings = settings
        self.attempts: list[dict] = []
        self.stage: str | None = None
        if settings.provider_name == "auto" and (settings._provider_router is None or settings._provider_router.settings is not settings):
            from backend.provider_routing import ProviderRouter
            settings._provider_router = ProviderRouter(settings)

    def identity(self):
        config = self.current_settings
        return {"provider": config.provider_name, "model": config.provider_model,
                "endpoint": config.provider_base_url, "returned_model": self.last_model}

    async def _probe(self, config, deadline):
        from backend.provider_routing import AvailabilityProbe
        candidate = config.model_copy(update={"provider_max_retries": 0, "provider_reasoning_effort": "none"})
        direct = Provider(candidate, transport=self.transport)
        started = time.monotonic()
        error = None
        try:
            result = await direct.structured([{"role": "user", "content": 'Return exactly {"ok": true}.'}],
                AvailabilityProbe, deadline=deadline, max_completion_tokens=128, temperature=0)
            if not result.ok:
                raise ProviderError("provider_probe_failed", "Provider failed the structured availability probe.")
        except ProviderError as caught:
            error = caught.code
            raise
        except asyncio.CancelledError:
            error = "provider_timeout"
            raise
        finally:
            self.attempts.append({"stage": self.stage, "purpose": "probe", "provider": config.provider_name,
                "model": config.provider_model, "endpoint": config.provider_base_url,
                "outcome": "failed" if error else "passed", "error_code": error,
                "elapsed_s": time.monotonic() - started})

    async def check(self, *, deadline=None):
        """Explicit startup/manual availability check. GET /health never calls this."""
        stop = min(deadline if deadline is not None else math.inf,
                   time.monotonic() + self.settings.request_deadline_s)
        try:
            if self.settings.provider_name == "auto":
                self.current_settings = await self.settings._provider_router.select(stop, self._probe)
            else:
                await self._probe(self.settings, stop)
        except TimeoutError:
            raise ProviderError("provider_timeout", "Provider selection deadline expired.", 504) from None
        return self.identity()

    async def structured(self, messages, response_model, *, deadline=None, max_completion_tokens=None, temperature=None):
        if self.settings.provider_name != "auto":
            return await self._structured(messages, response_model, deadline=deadline,
                max_completion_tokens=max_completion_tokens, temperature=temperature)
        stop = min(deadline if deadline is not None else math.inf,
                   time.monotonic() + self.settings.request_deadline_s)
        router = self.settings._provider_router
        tried = set()
        try:
            while len(tried) < len(self.settings.provider_names):
                candidate = await router.select(stop, self._probe, tried)
                self.current_settings = candidate
                tried.add(candidate.provider_name)
                # One payload attempt per provider avoids spending the entire
                # deadline on a failing provider's transport retries.
                direct = Provider(candidate.model_copy(update={"provider_max_retries": 0}), transport=self.transport)
                started = time.monotonic()
                failure = None
                try:
                    result = await direct.structured(messages, response_model, deadline=stop,
                        max_completion_tokens=max_completion_tokens, temperature=temperature)
                except ProviderError as error:
                    failure = error.code
                    repairable_content = error.code == "provider_invalid_response" or (
                        error.code == "provider_request_rejected" and error.upstream_code == "json_validate_failed")
                    if repairable_content:
                        raise
                    router.mark(candidate.provider_name, False, error.code)
                    if time.monotonic() >= stop:
                        raise ProviderError("provider_timeout", "Provider request deadline expired.", 504) from None
                    if len(tried) >= len(self.settings.provider_names):
                        raise
                    continue
                except asyncio.CancelledError:
                    failure = "provider_timeout"
                    raise
                finally:
                    self.current_settings = candidate
                    self.last_model = direct.last_model
                    if direct.last_usage:
                        self.last_usage = dict(direct.last_usage)
                    self.attempts.append({"stage": self.stage, "purpose": "request", "provider": candidate.provider_name,
                        "model": candidate.provider_model, "endpoint": candidate.provider_base_url,
                        "outcome": "failed" if failure else "passed", "error_code": failure,
                        "elapsed_s": time.monotonic() - started})
                router.mark(candidate.provider_name, True)
                return result
        except TimeoutError:
            raise ProviderError("provider_timeout", "Provider selection deadline expired.", 504) from None
        raise ProviderError("provider_unavailable", "No configured provider is currently available.")

    async def _structured(
        self,
        messages: list[Message],
        response_model: type[ResponseModel],
        *,
        deadline: float | None = None,
        max_completion_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ResponseModel:
        """Deadline is an absolute time.monotonic() value supplied by the caller.

        Pass Pydantic models with extra='forbid' and required (nullable if needed)
        fields, as required by strict JSON Schema. This method performs bounded
        transport retries; structured() handles routing and callers handle repair.
        """
        config = self.settings
        if not config.provider_configured:
            raise ProviderError("provider_not_configured", f"Set {config.provider_name.upper()}_API_KEY on the backend.")
        stop_at = min(
            math.inf if deadline is None else deadline,
            time.monotonic() + config.request_deadline_s,
        )
        remaining = stop_at - time.monotonic()
        if remaining <= 0:
            raise ProviderError("provider_timeout", "Provider request deadline expired.", 504)
        payload = {
            "model": config.provider_model,
            "messages": messages,
            "stream": False,
            "max_completion_tokens": max_completion_tokens or config.provider_max_completion_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        }
        if temperature is not None:
            if not math.isfinite(temperature) or not 0 <= temperature <= 2:
                raise ValueError("temperature must be finite and between 0 and 2")
            payload["temperature"] = temperature
        if config.provider_name == "llmtech":
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        else:
            payload.update(reasoning_effort=config.provider_reasoning_effort, reasoning_format="hidden")
        try:
            async with asyncio.timeout(remaining):
                async with httpx.AsyncClient(
                    transport=self.transport, follow_redirects=False,
                    headers={"Authorization": f"Bearer {config.provider_api_key.get_secret_value().strip()}"},
                ) as client:
                    for attempt in range(config.provider_max_retries + 1):
                        response = None
                        failure = ProviderError("provider_unavailable", "Provider is unavailable.")
                        call_budget = min(config.provider_call_timeout_s, stop_at - time.monotonic())
                        if call_budget <= 0:
                            raise TimeoutError
                        try:
                            # asyncio also bounds the whole attempt, including streamed body reads.
                            async with asyncio.timeout(call_budget):
                                response = await client.post(
                                    f"{config.provider_base_url}/chat/completions",
                                    json=payload, timeout=call_budget,
                                )
                        except (httpx.TimeoutException, TimeoutError):
                            failure = ProviderError("provider_timeout", "Provider call timed out.", 504)
                        except httpx.TransportError:
                            failure = ProviderError("provider_unavailable", "Cannot connect to provider.")
                        else:
                            if response.status_code in {401, 403}:
                                raise ProviderError("provider_authentication", "Provider rejected authentication or model access.")
                            if response.status_code == 402:
                                failure = ProviderError("provider_daily_limit", "Provider quota or balance is exhausted.", upstream_status=402)
                                failure.daily_limit = True
                                raise failure
                            if response.status_code != 429 and response.status_code < 500:
                                if response.status_code != 200:
                                    try:
                                        raw_code = response.json().get("error", {}).get("code")
                                    except (ValueError, AttributeError):
                                        raw_code = None
                                    safe_code = raw_code if isinstance(raw_code, str) and raw_code in {"json_validate_failed", "invalid_request_error", "schema_validation_error",
                                                                          "model_not_found", "rate_limit_exceeded"} else None
                                    raise ProviderError("provider_request_rejected", "Provider rejected the request or structured-output schema.",
                                                        upstream_status=response.status_code, upstream_code=safe_code)
                                try:
                                    response_data = response.json()
                                except ValueError:
                                    response_data = None
                                returned_model = response_data.get("model") if isinstance(response_data, dict) else None
                                self.last_model = returned_model if isinstance(returned_model, str) and returned_model.strip() else None
                                result = self._validate(response, response_model)
                                usage = response.json().get("usage", {})
                                self.last_usage = {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                                                   if isinstance(usage.get(k), int)} if isinstance(usage, dict) else {}
                                return result
                            failure = ProviderError("provider_unavailable", f"Provider returned HTTP {response.status_code} (rate limit or service failure).",
                                                    upstream_status=response.status_code)
                            if response.status_code == 429:
                                try:
                                    message = response.json().get("error", {}).get("message", "")
                                    failure.daily_limit = any(marker in message for marker in ("(TPD)", "(ITPD)", "(OTPD)", "tokens per day", "requests per day"))
                                except (ValueError, AttributeError, TypeError):
                                    pass
                                if failure.daily_limit:
                                    failure.code = "provider_daily_limit"
                                    raise failure
                        if attempt == config.provider_max_retries:
                            raise failure from None
                        delay = _retry_delay(response, attempt)
                        if time.monotonic() + delay >= stop_at:
                            raise TimeoutError
                        await asyncio.sleep(delay)
        except TimeoutError:
            raise ProviderError("provider_timeout", "Provider request deadline expired.", 504) from None
        raise AssertionError("Unreachable retry state")

    @staticmethod
    def _validate(response: httpx.Response, response_model: type[ResponseModel]) -> ResponseModel:
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid response envelope")
            choice = data["choices"][0]
            if not isinstance(choice, dict):
                raise ValueError("Invalid choice")
            message = choice["message"]
            if not isinstance(message, dict):
                raise ValueError("Invalid message")
            if choice.get("finish_reason") != "stop" or message.get("refusal"):
                raise ValueError("Incomplete or refused response")
            content = message["content"]
            if not isinstance(content, str):
                raise ValueError("Missing JSON content")
            return response_model.model_validate_json(content, strict=True)
        except (ValueError, TypeError, KeyError, IndexError, ValidationError, json.JSONDecodeError) as validation_error:
            error = ProviderError("provider_invalid_response", "Provider response failed local validation.", 502)
            if isinstance(validation_error, ValidationError):
                error.validation_errors = [{"loc": list(item["loc"]), "type": item["type"], "message": item["msg"]}
                                           for item in validation_error.errors()]
            # Retain only model content for an explicit local ingestion diagnostic, never headers/error bodies.
            try:
                error.invalid_content = response.json()["choices"][0]["message"]["content"]
                error.finish_reason = response.json()["choices"][0].get("finish_reason")
            except (ValueError, TypeError, KeyError, IndexError):
                pass
            raise error from None
