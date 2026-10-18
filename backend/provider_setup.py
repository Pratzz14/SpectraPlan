"""Configure backend provider selection: python -m backend.provider_setup --public-trial --check."""

import argparse
import asyncio
import json
import re

import httpx
from dotenv import set_key
from pydantic import SecretStr

from backend.config import PROJECT_ROOT, Settings


def with_public_trial(settings: Settings) -> Settings:
    """Explicit setup only; request routing never fetches or replaces credentials."""
    if settings.usable_key(settings.llmtech_api_key):
        return settings
    response = httpx.get("https://llmtech.eu/docs/", timeout=30, follow_redirects=False)
    response.raise_for_status()
    match = re.search(r"lt-trial-[0-9a-f]+", response.text)
    if not match:
        raise ValueError("No public LLMTech trial credential is available")
    return Settings(_env_file=None, **{**settings.model_dump(), "llmtech_api_key": SecretStr(match.group())})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["auto", "gemini", "llmtech", "groq"], default="auto")
    parser.add_argument("--public-trial", action="store_true", help="Fill a missing LLMTech key from its documented public trial")
    parser.add_argument("--check", action="store_true", help="Make a small synthetic live structured-output check")
    args = parser.parse_args()
    try:
        settings = Settings().for_provider(args.mode)
        if args.public_trial:
            settings = with_public_trial(settings)
            set_key(str(PROJECT_ROOT / ".env"), "LLMTECH_API_KEY", settings.llmtech_api_key.get_secret_value())
        set_key(str(PROJECT_ROOT / ".env"), "PROVIDER_NAME", args.mode)
        print("Saved backend provider configuration. Credential values are never printed.")
        if args.check:
            from backend.provider import Provider, ProviderError
            adapter = Provider(settings)
            try:
                identity = asyncio.run(adapter.check())
                print(json.dumps({"outcome": "working", **identity, "checks": adapter.attempts}))
            except ProviderError as error:
                print(json.dumps({"outcome": "unavailable", "code": error.code, "checks": adapter.attempts}))
                return 1
    except (httpx.HTTPError, ValueError):
        parser.error("Provider setup failed; check configuration or public-trial availability. No credential values were logged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
