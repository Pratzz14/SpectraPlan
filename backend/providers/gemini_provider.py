"""Gemini Interactions wire adapter; callers own validation and the shared deadline."""

import re

import httpx


class GeminiRequestError(Exception):
    def __init__(self, status_code, *, daily_limit=False):
        self.status_code = status_code
        self.daily_limit = daily_limit


def interaction_payload(messages, schema, settings, max_tokens):
    instructions, turns = [], []
    for message in messages:
        if message["role"] == "system":
            instructions.append(message["content"])
            continue
        content = message["content"]
        if isinstance(content, str):
            parts = [{"type": "text", "text": content}]
        else:
            parts = []
            for part in content:
                if part["type"] == "text":
                    parts.append({"type": "text", "text": part["text"]})
                elif part["type"] == "image_url":
                    url = part["image_url"]["url"]
                    match = re.fullmatch(r"data:([^;]+);base64,(.+)", url, re.DOTALL)
                    if not match:
                        raise ValueError("Gemini ingestion requires an inline source image")
                    parts.append({"type": "image", "mime_type": match[1], "data": match[2]})
                else:
                    raise ValueError("Unsupported model input content")
        # Each call regenerates from the original input. Repair feedback is user text;
        # avoid prefilled model turns and server-side conversation state.
        if message["role"] == "assistant":
            continue
        turns.extend(parts)
    return {"model": settings.provider_model.removeprefix("models/"),
            "system_instruction": "\n\n".join(instructions), "input": turns,
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
            "generation_config": {"max_output_tokens": max_tokens,
                                  "thinking_level": settings.gemini_thinking_level},
            "store": False}


async def create_interaction(payload, settings, timeout, client=None):
    if client is not None:
        return await client.aio.interactions.create(**payload, timeout=timeout)
    # Use the native Interactions wire format with explicit HTTP timeouts and no
    # hidden SDK retries; every transport attempt remains in the shared deadline.
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as http:
        response = await http.post(settings.provider_base_url + "/v1beta/interactions",
            headers={"x-goog-api-key": settings.gemini_api_key.get_secret_value()}, json=payload)
        if response.status_code != 200:
            # Never retain upstream error text, which can echo request material.
            daily_limit = False
            if response.status_code == 429:
                try:
                    message = response.json().get("error", {}).get("message", "").casefold()
                    daily_limit = "per_day" in message or "per day" in message
                except (ValueError, AttributeError, TypeError):
                    pass
            raise GeminiRequestError(response.status_code, daily_limit=daily_limit)
        return response.json()


def response_content(response):
    """Support current output_text and earlier SDK outputs envelopes."""
    data = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
    if not isinstance(data, dict):
        data = vars(response)
    text = data.get("output_text") or data.get("text")
    if not text:
        text = "".join(part.get("text", "") for step in data.get("steps", [])
                       if step.get("type") == "model_output" for part in step.get("content", [])
                       if part.get("type") == "text")
    if not text:
        text = "".join(part.get("text", "") for part in data.get("outputs", []) if part.get("type") == "text")
    usage = data.get("usage") or {}
    counts = {target: usage[source] for target, source in (
        ("prompt_tokens", "total_input_tokens"), ("completion_tokens", "total_output_tokens"),
        ("total_tokens", "total_tokens")) if isinstance(usage.get(source), int)}
    status = data.get("status", "completed")
    return text, data.get("model"), counts, status
