"""Manual live extraction check: python -m backend.smoke_extraction.

Uses enquiry inputs only, never organizer worked answers or technical retrieval.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from backend.agent import EXTRACTION_PROMPT, EXTRACTION_PROMPT_VERSION, ExtractionOutput, extract_case
from backend.config import PROJECT_ROOT, Settings
from backend.provider import Provider, ProviderError

SYNTHETIC_CASES = [
    {"case_id": "multi_stream", "description": "Stream A is a powder blend containing API and excipients. We want to follow API concentration. Stream B is an opaque liquid milk product; we want to measure fat and protein. Both streams must retain independent laboratory checks. Only stream A runs at 35 C. No temperature has been supplied for stream B."},
    {"case_id": "capability_claim", "description": "We own a fluorescence instrument. We believe it can measure protein accurately in milk, but we have not validated that relationship. We want to track protein concentration and propose trying fluorescence first."},
    {"case_id": "ambiguous_units", "description": "We have a slurry at 20-40 C and 2 bar(g). We want to measure water content in the range 5-10%, but the concentration basis has not been defined. Our response time requirement is '2', with the units still undecided. We have not agreed an error limit."},
]


async def run_cases(settings: Settings, selected: set[str] | None = None) -> tuple[dict, int]:
    cases = json.loads((PROJECT_ROOT / "evaluation/development.json").read_text(encoding="utf-8"))["cases"] + SYNTHETIC_CASES
    if selected:
        unknown = selected - {case["case_id"] for case in cases}
        if unknown:
            raise ValueError(f"Unknown case IDs: {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["case_id"] in selected]
    record = {
        "run_id": uuid4().hex,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": settings.provider_name, "model": settings.provider_model if settings.provider_name != "auto" else None,
        "endpoint": settings.provider_base_url if settings.provider_name != "auto" else None,
        "prompt_version": EXTRACTION_PROMPT_VERSION,
        "prompt_sha256": hashlib.sha256(EXTRACTION_PROMPT.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps(ExtractionOutput.model_json_schema(), sort_keys=True).encode("utf-8")).hexdigest(),
        "settings": {"call_timeout_s": settings.provider_call_timeout_s,
                     "request_deadline_s": settings.request_deadline_s,
                     "max_completion_tokens": settings.provider_max_completion_tokens,
                     "extraction_max_completion_tokens": settings.extraction_max_completion_tokens,
                     "max_retries": settings.provider_max_retries},
        "review_status": "pending_manual_semantic_review", "cases": [],
    }
    failed = False
    for case in cases:
        adapter = Provider(settings)
        result = {**case, "outcome": "failed", "facts": None, "error": None}
        try:
            facts = await extract_case(case["description"], settings, provider=adapter)
            result.update(outcome="passed_mechanical_validation", facts=facts.model_dump(), usage=adapter.last_usage)
        except ProviderError as error:
            failed = True
            result["error"] = {"code": error.code, "message": str(error),
                               "upstream_status": error.upstream_status, "upstream_code": error.upstream_code}
            result["validation_errors"] = getattr(error, "validation_errors", [])
            result["invalid_content"] = getattr(error, "invalid_content", None)
        result.update(provider_identity=adapter.identity(), provider_attempts=adapter.attempts)
        record["cases"].append(result)
    return record, int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", dest="cases", help="D01, D02, multi_stream, capability_claim, ambiguous_units; repeatable")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs/extraction")
    parser.add_argument("--provider", choices=["auto", "gemini", "groq", "llmtech"], help="Explicit run-only override; saved configuration is unchanged")
    parser.add_argument("--public-trial", action="store_true", help="Use LLMTech's documented public trial only if no LLMTech key is configured")
    args = parser.parse_args()
    try:
        settings = Settings()
        if args.provider:
            settings = settings.for_provider(args.provider)
        if args.public_trial:
            from backend.provider_setup import with_public_trial
            settings = with_public_trial(settings)
        record, code = asyncio.run(run_cases(settings, set(args.cases) if args.cases else None))
    except httpx.HTTPError:
        parser.error("Cannot retrieve LLMTech public trial configuration")
    except ValueError as error:
        parser.error(str(error))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = args.output_dir / f"{stamp}_{record['run_id']}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for case in record["cases"]:
        print(f"{case['case_id']}: {case['outcome']}" + (f" ({case['error']['code']})" if case["error"] else ""))
    print(f"Saved {path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
