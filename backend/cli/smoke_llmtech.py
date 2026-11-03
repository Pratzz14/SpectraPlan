"""Explicit LLMTech compatibility test using synthetic content only.

python -m backend.cli.smoke_llmtech --public-trial
No project source documents are read or sent. Production configuration is unchanged.
"""

from backend.prompts import load_prompt

import argparse
import asyncio
import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf

from backend.core.config import PROJECT_ROOT, Settings
from backend.schemas.knowledge_models import PageExtraction, PageVerification
from backend.services.knowledge.knowledge_store import write_json
from backend.providers.provider import Provider
from backend.cli.smoke_provider import SmokeExtraction

BASE_URL = "https://api.llmtech.eu/v1"
MODEL = "nvidia/Qwen3.8-27B-NVFP4"


def synthetic_image() -> str:
    document = pymupdf.open()
    try:
        page = document.new_page(width=720, height=350)
        page.insert_text((25, 35), "SYNTHETIC TEST DIAGRAM", fontsize=22)
        page.insert_text((25, 65), "Invented test ranges; not equipment specifications.", fontsize=14)
        page.draw_rect(pymupdf.Rect(30, 100, 690, 180), color=(0, .4, .5), fill=(.9, .98, .98))
        page.insert_text((50, 145), "Silica test band: 400-2400 nm", fontsize=24)
        page.draw_rect(pymupdf.Rect(30, 210, 690, 290), color=(.2, .5, .2), fill=(.93, .98, .9))
        page.insert_text((50, 255), "PIR test band: 3-16 um", fontsize=24)
        data = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).tobytes("jpeg")
        return "data:image/jpeg;base64," + base64.b64encode(data).decode()
    finally:
        document.close()


async def run(*, public_trial=False) -> tuple[dict, int]:
    settings = Settings().for_provider("llmtech")
    if public_trial:
        from backend.cli.provider_setup import with_public_trial
        settings = with_public_trial(settings)
    endpoint, model_id = settings.provider_base_url, settings.provider_model
    record = {"run_id": uuid4().hex, "generated_at": datetime.now(timezone.utc).isoformat(),
              "provider": "llmtech", "endpoint": endpoint, "requested_model": model_id,
              "data_scope": "Synthetic text and a generated synthetic diagram only; no AFS content",
              "test_scope": "API/schema/vision compatibility, not acceptance of all extracted scientific fields",
              "production_configuration_changed": False, "tests": [], "outcome": "failed"}
    async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
        key = settings.llmtech_api_key.get_secret_value().strip()
        if not key:
            raise ValueError("Set backend-only LLMTECH_API_KEY or explicitly use --public-trial")
        record["key_source"] = "backend_configuration_or_explicit_public_trial"

        async def request(name, messages, model, budget):
            payload = {"model": model_id, "messages": messages, "stream": False,
                       "chat_template_kwargs": {"enable_thinking": False}, "max_completion_tokens": budget,
                       "response_format": {"type": "json_schema", "json_schema": {
                           "name": model.__name__, "strict": True, "schema": model.model_json_schema()}}}
            started = asyncio.get_running_loop().time()
            result = await client.post(endpoint + "/chat/completions",
                                       headers={"Authorization": "Bearer " + key}, json=payload)
            metadata = {"test": name, "http_status": result.status_code,
                        "elapsed_s": round(asyncio.get_running_loop().time() - started, 2),
                        "requested_max_completion_tokens": budget}
            record["tests"].append(metadata)
            if result.status_code != 200:
                # No upstream body, prompt or authorization header is written to diagnostics.
                metadata["outcome"] = "http_failure"
                raise ValueError(f"{name} returned HTTP {result.status_code}")
            output = Provider._validate(result, model)
            envelope = result.json()
            metadata.update(outcome="schema_valid", returned_model=envelope.get("model"),
                            finish_reason=envelope["choices"][0].get("finish_reason"),
                            usage=envelope.get("usage", {}), validated_response=output.model_dump())
            return output

        try:
            simple = await request("strict_text_extraction", [
                {"role": "system", "content": load_prompt("provider_extraction_smoke.txt")},
                {"role": "user", "content": "We want to measure moisture in a powder."}], SmokeExtraction, 4096)
            if simple.sample_phase.lower() != "powder" or simple.target.lower() != "moisture":
                raise ValueError("Synthetic text facts were not preserved")
            image = synthetic_image()
            source = {"source_id": "SYNTHETIC", "file_name": "generated-test-fixture", "source_role": "technical",
                      "physical_pdf_page_1_based": 1,
                      "blocks": [{"block_id": "b001", "text": "Synthetic sample: powder. Target: moisture."}],
                      "note": "The attached diagram is invented test data, not real equipment specifications."}
            content = [{"type": "text", "text": json.dumps(source)}, {"type": "image_url", "image_url": {"url": image}}]
            extraction = await request("actual_ingestion_schema_with_synthetic_image", [
                {"role": "system", "content": load_prompt("legacy_knowledge_extract.txt")},
                {"role": "user", "content": content}], PageExtraction, 4096)
            transcription = " ".join(figure.transcription for figure in extraction.figures)
            numbers = set(re.findall(r"\d+", transcription))
            if not extraction.text_groups or not extraction.figures or not {"400", "2400", "3", "16"}.issubset(numbers):
                raise ValueError("Synthetic diagram labels/ranges were not fully transcribed")
            observations = []
            for index, group in enumerate([*extraction.text_groups, *extraction.figures]):
                for fact in group.facts:
                    for quantity in fact.quantities:
                        if not re.search(r"\d", quantity.value):
                            observations.append({"group": index, "issue": "Text value misclassified as numerical quantity", "value": quantity.value})
                        if quantity.unit and quantity.unit not in quantity.source_quote:
                            observations.append({"group": index, "issue": "Quantity unit absent from its supporting quote", "unit": quantity.unit})
            record["semantic_observations"] = observations
            numbered = [{"candidate_index": i, "candidate": c.model_dump()} for i, c in enumerate(extraction.candidates)]
            verify_content = [{"type": "text", "text": json.dumps(source) + "\nCandidates:\n" + json.dumps(numbered)}, content[1]]
            verification = await request("actual_verification_schema_with_synthetic_image", [
                {"role": "system", "content": load_prompt("legacy_knowledge_verify.txt")},
                {"role": "user", "content": verify_content}], PageVerification, 2048)
            if sorted(v.candidate_index for v in verification.verdicts) != list(range(len(extraction.candidates))):
                raise ValueError("Verification did not cover every candidate")
            record["verification_statuses"] = [v.status for v in verification.verdicts]
            record["outcome"] = "passed"
            return record, 0
        except Exception as error:
            # Sanitized local errors only; never store raw HTTP error bodies or a key.
            record["error"] = str(error).replace(key, "<redacted>") if isinstance(error, ValueError) else type(error).__name__
            return record, 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-trial", action="store_true")
    args = parser.parse_args()
    try:
        record, code = asyncio.run(run(public_trial=args.public_trial))
    except Exception as error:
        print("LLMTech smoke setup failed: " + type(error).__name__)
        return 1
    path = PROJECT_ROOT / "outputs" / "provider_smoke" / (
        "llmtech_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + record["run_id"] + ".json")
    write_json(path, record)
    print(json.dumps({"outcome": record["outcome"], "tests": [{k: t[k] for k in ("test", "http_status", "outcome") if k in t}
                                                            for t in record["tests"]], "error": record.get("error"),
                      "saved_record": str(path)}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
