"""Structured Groq adapter with one shared deadline and sanitized failures."""

import asyncio
import json
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from backend.config import Settings

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class ProviderError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 503):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


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

    async def structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[ResponseModel],
        *,
        deadline: float | None = None,
        max_completion_tokens: int | None = None,
    ) -> ResponseModel:
        """Deadline is an absolute time.monotonic() value supplied by the caller.

        Pass Pydantic models with extra='forbid' and required (nullable if needed)
        fields, as required by Groq strict JSON Schema. No fallback or repair is
        hidden inside this transport adapter.
        """
        config = self.settings
        if not config.provider_configured:
            raise ProviderError("provider_not_configured", "Set GROQ_API_KEY on the backend.")
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
            "reasoning_effort": config.provider_reasoning_effort,
            "reasoning_format": "hidden",
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
        try:
            async with asyncio.timeout(remaining):
                async with httpx.AsyncClient(
                    transport=self.transport, follow_redirects=False,
                    headers={"Authorization": f"Bearer {config.groq_api_key.get_secret_value().strip()}"},
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
                            if response.status_code != 429 and response.status_code < 500:
                                if response.status_code != 200:
                                    raise ProviderError("provider_request_rejected", "Provider rejected the request or structured-output schema.")
                                return self._validate(response, response_model)
                            failure = ProviderError("provider_unavailable", "Provider rate limit or service failure.")
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
        except (ValueError, TypeError, KeyError, IndexError, ValidationError, json.JSONDecodeError):
            raise ProviderError("provider_invalid_response", "Provider response failed local validation.", 502) from None
