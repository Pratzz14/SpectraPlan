"""Manual, corpus-independent live test: python -m backend.smoke_provider."""

import asyncio
import argparse
import json
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from backend.config import Settings
from backend.provider import Provider, ProviderError


class SmokeExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sample_phase: str
    target: str


async def run_smoke(settings: Settings) -> tuple[dict, int]:
    record = {
        "run_id": uuid4().hex,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": settings.provider_name,
        "model": settings.provider_model,
        "settings": {
            "reasoning_effort": settings.provider_reasoning_effort,
            "strict_json_schema": True,
            "call_timeout_s": settings.provider_call_timeout_s,
            "deadline_s": settings.request_deadline_s,
            "max_retries": settings.provider_max_retries,
            "max_completion_tokens": 2048,
        },
        "outcome": "unresolved",
        "validated_response": None,
        "error": None,
    }
    adapter = Provider(settings)
    try:
        result = await adapter.structured(
            [
                {"role": "system", "content": "Copy the explicitly stated sample phase and target verbatim. Preserve the word powder as powder, not solid. Return JSON matching the supplied schema."},
                {"role": "user", "content": "We want to measure moisture in a powder."},
            ],
            SmokeExtraction,
            max_completion_tokens=2048,
            temperature=0,
        )
        record["validated_response"] = result.model_dump()
        if result.sample_phase.lower().strip() != "powder" or result.target.lower().strip() != "moisture":
            raise ProviderError("smoke_content_mismatch", "Synthetic extraction did not preserve the stated facts.", 502)
        record.update(outcome="passed", validated_response=result.model_dump())
        return record, 0
    except ProviderError as error:
        record["error"] = {"code": error.code, "message": str(error)}
        return record, 1
    finally:
        record.update(adapter.identity(), provider_mode=settings.provider_name, attempts=adapter.attempts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["auto", "groq", "llmtech"])
    parser.add_argument("--all", action="store_true", help="Test each configured provider independently with synthetic data")
    args = parser.parse_args()
    settings = Settings()
    if args.provider:
        settings = settings.for_provider(args.provider)
    if args.all:
        async def check_all():
            records = []
            for name in settings.provider_order.split(","):
                candidate = settings.for_provider(name)
                if candidate.provider_configured:
                    value, _ = await run_smoke(candidate)
                    records.append(value)
            return {"run_id": uuid4().hex, "providers": records}, int(not any(r["outcome"] == "passed" for r in records))
        record, code = asyncio.run(check_all())
    else:
        record, code = asyncio.run(run_smoke(settings))
    settings.smoke_output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = settings.smoke_output_dir / f"{stamp}_{record['run_id']}.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    print(f"Saved smoke record: {path.name}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
