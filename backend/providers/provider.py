"""Structured provider adapter with one shared deadline and sanitized failures."""


import asyncio
import copy
import json
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar, TypedDict

import httpx
from pydantic import BaseModel, ValidationError

from backend.core.config import Settings

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
        self.trace_events: list[dict] = []
        self.stage: str | None = "provider"
        self.on_event = None

    def emit(self, event_type, payload):
        event = {"stage": self.stage or "provider", "event_type": event_type,
                 "created_at": datetime.now(timezone.utc).isoformat(), "payload": copy.deepcopy(payload)}
        self.trace_events.append(event)
        if self.on_event is not None:
            self.on_event(event)

    def reject_stage(self, errors, *, exhausted=False):
        self.emit("validation_failed", {"errors": errors, "exhausted": exhausted,
                                        **self.identity()})

    def identity(self):
        config = self.current_settings
        return {"provider": config.provider_name, "model": config.provider_model,
                "endpoint": config.provider_base_url, "returned_model": self.last_model}

    async def structured(
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
        transport retries; callers handle bounded content repair.
        """
        config = self.settings
        if not config.provider_configured:
            raise ProviderError("provider_not_configured", f"Set {config.provider_name.upper()}_API_KEY on the backend.")
        stop_at = min(deadline if deadline is not None else math.inf,
                      time.monotonic() + config.request_deadline_s)
        max_tokens = max_completion_tokens or config.provider_max_completion_tokens
        payload = {"model": config.provider_model, "messages": messages, "stream": False,
            "max_tokens": max_tokens, "response_format": {"type": "json_schema",
            "json_schema": {"name": response_model.__name__, "strict": True,
                            "schema": response_model.model_json_schema()}}}
        if temperature is not None:
            if not math.isfinite(temperature) or not 0 <= temperature <= 2:
                raise ValueError("temperature must be finite and between 0 and 2")
            payload["temperature"] = temperature
        payload["enable_thinking"] = False
        for attempt in range(config.provider_max_retries + 1):
            budget = min(config.provider_call_timeout_s, stop_at - time.monotonic())
            if budget <= 0:
                raise ProviderError("provider_timeout", "Provider request deadline expired.", 504)
            started = time.monotonic()
            request_record = {**self.identity(), "attempt": attempt, "request": payload}
            self.attempts.append({"stage": self.stage, "purpose": "request", "provider": "dashscope", "model": config.provider_model, "endpoint": config.provider_base_url, "attempt": attempt})
            self.emit("provider_request", request_record)
            response = None
            try:
                async with asyncio.timeout(budget):
                    async with httpx.AsyncClient(transport=self.transport, follow_redirects=False,
                        headers={"Authorization": f"Bearer {config.provider_api_key.get_secret_value().strip()}"}) as client:
                        response = await client.post(f"{config.provider_base_url}/chat/completions",
                                                     json=payload, timeout=budget)
                    if response.status_code != 200:
                        status = response.status_code
                        safe_code = None
                        daily = status == 402
                        try:
                            upstream = response.json().get("error", {})
                            raw_code = upstream.get("code")
                            if raw_code in {"json_validate_failed", "invalid_request_error", "schema_validation_error", "model_not_found", "rate_limit_exceeded"}:
                                safe_code = raw_code
                            message = upstream.get("message", "")
                            daily |= status == 429 and any(marker in message for marker in
                                ("(TPD)", "(ITPD)", "(OTPD)", "tokens per day", "requests per day"))
                        except (ValueError, AttributeError, TypeError):
                            pass
                        code = ("provider_authentication" if status in {401, 403} else
                                "provider_daily_limit" if daily else
                                "provider_unavailable" if status == 429 or status >= 500 else "provider_request_rejected")
                        error = ProviderError(code, f"Provider returned HTTP {status}.", upstream_status=status, upstream_code=safe_code)
                        error.daily_limit = daily
                        raise error
                    try:
                        data = response.json()
                    except ValueError:
                        data = {}
                    returned_model = data.get("model") if isinstance(data, dict) else None
                    self.last_model = returned_model if isinstance(returned_model, str) and returned_model.strip() else None
                    usage = data.get("usage", {}) if isinstance(data, dict) else {}
                    self.last_usage = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                                       if isinstance(usage, dict) and isinstance(usage.get(key), int)}
                    try:
                        raw = response.json().get("choices", [{}])[0].get("message", {}).get("content")
                    except (ValueError, AttributeError, IndexError, TypeError):
                        raw = response.text
                    if raw is None:
                        raw = response.text
                    self.emit("provider_response", {**self.identity(), "attempt": attempt,
                        "raw_content": raw, "usage": self.last_usage, "elapsed_s": time.monotonic() - started})
                    result = self._validate(response, response_model)
                    self.emit("provider_validated", {**self.identity(), "validated_output": result.model_dump(mode="json")})
                    return result
            except asyncio.CancelledError:
                self.emit("provider_error", {**self.identity(), "code": "cancelled", "elapsed_s": time.monotonic() - started})
                raise
            except (TimeoutError, httpx.TimeoutException):
                failure = ProviderError("provider_timeout", "Provider call timed out.", 504)
            except httpx.TransportError:
                failure = ProviderError("provider_unavailable", "Cannot connect to provider.")
            except ProviderError as caught:
                failure = caught
            self.emit("provider_error", {**self.identity(), "attempt": attempt, "code": failure.code,
                "upstream_status": failure.upstream_status, "validation_errors": getattr(failure, "validation_errors", []),
                "elapsed_s": time.monotonic() - started})
            if (attempt == config.provider_max_retries or failure.code not in {"provider_timeout", "provider_unavailable"}):
                raise failure from None
            delay = _retry_delay(response, attempt)
            if time.monotonic() + delay >= stop_at:
                raise ProviderError("provider_timeout", "Provider request deadline expired.", 504)
            await asyncio.sleep(delay)
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
