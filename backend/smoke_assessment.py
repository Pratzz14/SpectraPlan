"""Live development pipeline: python -m backend.smoke_assessment --provider llmtech --public-trial."""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from backend.agent import (
    EXTRACTION_PROMPT, EXTRACTION_PROMPT_VERSION, PIPELINE_VERSION, SYNTHESIS_PROMPT,
    SYNTHESIS_PROMPT_VERSION, AssessmentValidationError, ExtractionOutput, SynthesisOutput, assess_case,
)
from backend.config import PROJECT_ROOT, Settings
from backend.models import AssessmentRun
from backend.evidence import CorpusUnavailable
from backend.knowledge_store import digest, file_hash, write_json
from backend.provider import Provider, ProviderError
from backend.retrieval import CaseRetrievalService, RetrievalTimeout


async def run_cases(settings: Settings, selected: set[str] | None = None, *, use_api: bool = False) -> tuple[dict, int]:
    inputs = PROJECT_ROOT / "evaluation/development.json"
    cases = json.loads(inputs.read_text(encoding="utf-8"))["cases"]
    selected = {"D01", "D02"} if selected is None else selected
    if not selected or selected - {case["case_id"] for case in cases}:
        raise ValueError("Select existing development cases")
    record = {
        "run_id": uuid4().hex, "generated_at": datetime.now(timezone.utc).isoformat(),
        "development_only": True, "pipeline_version": PIPELINE_VERSION, "transport": "asgi_api" if use_api else "python",
        "provider": settings.provider_name, "model": settings.provider_model if settings.provider_name != "auto" else None,
        "endpoint": settings.provider_base_url if settings.provider_name != "auto" else None, "input_file_sha256": file_hash(inputs),
        "prompt_versions": {"extraction": EXTRACTION_PROMPT_VERSION, "synthesis": SYNTHESIS_PROMPT_VERSION},
        "prompt_sha256": {"extraction": digest(EXTRACTION_PROMPT.encode()), "synthesis": digest(SYNTHESIS_PROMPT.encode())},
        "schema_sha256": {"extraction": digest(ExtractionOutput.model_json_schema()),
                          "synthesis_template": digest(SynthesisOutput.model_json_schema())},
        "settings": {"call_timeout_s": settings.provider_call_timeout_s,
                     "request_deadline_s": settings.request_deadline_s, "max_retries": settings.provider_max_retries,
                     "max_completion_tokens": settings.provider_max_completion_tokens,
                     "extraction_max_completion_tokens": settings.extraction_max_completion_tokens,
                     "synthesis_max_completion_tokens": settings.synthesis_max_completion_tokens,
                     "synthesis_temperature": 0},
        "review_status": "pending_source_support_inspection", "cases": [],
    }
    service = CaseRetrievalService(settings)
    if use_api:
        from backend.main import create_app
        application = create_app(settings)
    failed = False
    for case in cases:
        if case["case_id"] not in selected:
            continue
        adapter = Provider(settings)
        started = time.monotonic()
        checkpoints = {}
        stage_outcomes = {}
        active_stage = "extraction"

        def checkpoint(stage, value):
            nonlocal active_stage
            checkpoints[stage] = value.model_dump()
            stage_outcomes[stage] = "passed_basic_checks"
            active_stage = {"extraction": "retrieval", "retrieval": "synthesis", "synthesis": "complete"}[stage]
            print(f"{case['case_id']}: {stage} passed basic checks", flush=True)

        result = {**case, "input_sha256": digest(case["description"].encode()),
                  "outcome": "failed", "result": None, "error": None}
        try:
            if use_api:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://assessment.local") as client:
                    response = await client.post("/api/assess", json={"description": case["description"]})
                    result["http_status"] = response.status_code
                    output = AssessmentRun.model_validate(response.json())
            else:
                output = await assess_case(case["description"], settings, provider=adapter,
                                           retrieval_service=service, on_stage=checkpoint)
            result.update(outcome="passed_basic_checks" if output.run_status == "complete" else "incomplete",
                          result=output.model_dump())
            if output.errors:
                failed = True
                result["error"] = output.errors[0].model_dump()
                result["stage_outputs"] = checkpoints
                stage_outcomes[output.errors[0].stage] = "failed"
        except (ProviderError, AssessmentValidationError, CorpusUnavailable, RetrievalTimeout) as error:
            failed = True
            stage_outcomes[active_stage] = "failed"
            result["stage_outputs"] = checkpoints
            if isinstance(error, ProviderError):
                result["error"] = {"code": error.code, "message": str(error),
                                   "upstream_status": error.upstream_status, "upstream_code": error.upstream_code}
            else:
                result["error"] = {"code": type(error).__name__, "message": str(error)}
            if isinstance(error, AssessmentValidationError):
                result["reference_errors"] = error.errors
            feedback = getattr(error, "validation_errors", None)
            if feedback:
                key = settings.provider_api_key.get_secret_value().strip()
                safe_feedback = json.dumps(feedback, ensure_ascii=False)
                result["validation_errors"] = json.loads(safe_feedback.replace(key, "<redacted>") if key else safe_feedback)
            # Model output only; never HTTP bodies or authorization headers.
            content = getattr(error, "invalid_content", None)
            if isinstance(content, str):
                key = settings.provider_api_key.get_secret_value().strip()
                result["invalid_content"] = content.replace(key, "<redacted>") if key else content
        result.update(stage_outcomes=stage_outcomes, elapsed_s=time.monotonic() - started)
        record["cases"].append(result)
        print(f"{case['case_id']}: {result['outcome']}", flush=True)
    return record, int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", dest="cases", help="Development case ID; repeatable; defaults to D01 and D02")
    parser.add_argument("--provider", choices=["auto", "gemini", "groq", "llmtech"], help="Run-only override")
    parser.add_argument("--public-trial", action="store_true", help="Explicit LLMTech public trial if no backend key is configured")
    parser.add_argument("--api", action="store_true", help="Exercise POST /api/assess through ASGI with live provider/retrieval")
    parser.add_argument("--request-deadline-s", type=float, default=180)
    parser.add_argument("--call-timeout-s", type=float, default=60)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs/assessment")
    args = parser.parse_args()
    try:
        settings = Settings()
        overrides = {"request_deadline_s": args.request_deadline_s, "provider_call_timeout_s": args.call_timeout_s}
        if args.provider:
            settings = settings.for_provider(args.provider)
        # Validate overrides instead of bypassing Settings constraints with model_copy.
        settings = Settings(_env_file=None, **{**settings.model_dump(), **overrides})
        if args.public_trial:
            from backend.provider_setup import with_public_trial
            settings = with_public_trial(settings)
        record, code = asyncio.run(run_cases(settings, set(args.cases) if args.cases else None, use_api=args.api))
    except httpx.HTTPError:
        parser.error("Cannot retrieve LLMTech public trial configuration")
    except ValueError as error:
        # Settings validation can contain input values; never print settings/secrets.
        parser.error("Invalid diagnostic configuration or development case selection: " + type(error).__name__)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = args.output_dir / f"{stamp}_{record['run_id']}.json"
    write_json(path, record)
    print(f"Saved {path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
