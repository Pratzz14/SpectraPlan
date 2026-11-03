"""Run development or final scenarios through the public assessment API.

Case identifiers stay in the runner and artifact filenames. Only the original
scenario description is submitted to the application.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile
import xml.etree.ElementTree as ElementTree

import httpx

from backend.pipelines.assessment.pipeline import EXTRACTION_PROMPT, EXTRACTION_PROMPT_VERSION, PIPELINE_VERSION, SYNTHESIS_PROMPT, SYNTHESIS_PROMPT_VERSION, SynthesisOutput, ExtractionOutput
from backend.core.config import PROJECT_ROOT, Settings
from backend.services.search.evidence import CorpusUnavailable
from backend.services.knowledge.knowledge_store import digest, file_hash, write_json
from backend.main import create_app
from backend.schemas.models import AssessmentRun
from backend.services.search.retrieval import EMBEDDING_MODEL, RETRIEVAL_VERSION
from backend.pipelines.assessment.validation import _check_synthesis_inputs, validate_extraction, validate_final


DEVELOPMENT_INPUT = PROJECT_ROOT / "evaluation/development.json"
FINAL_INPUT = PROJECT_ROOT / "evaluation/final.json"
SOURCE_ROOT = PROJECT_ROOT / "knowledge/original_sources"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/development"
FINAL_OUTPUT = PROJECT_ROOT / "outputs/runs"
FINAL_CASE_IDS = {f"H{index:02d}" for index in range(1, 7)}
MANIFEST_VERSION = "evaluation-v2"
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def source_paragraphs(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    namespace = {"w": WORD_NAMESPACE}
    return [
        "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
        for paragraph in root.findall(".//w:body/w:p", namespace)
    ]


def load_development_cases(path: Path = DEVELOPMENT_INPUT) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("source_file") != "AFS_Examples_and_Reference.docx":
        raise ValueError("Development input source_file must identify the supplied examples document")
    source_path = SOURCE_ROOT / data["source_file"]
    if not source_path.is_file() or file_hash(source_path) != data.get("source_sha256"):
        raise ValueError("Development source hash does not match the supplied examples document")
    paragraphs = source_paragraphs(source_path)
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) != 8 or [case.get("case_id") for case in cases] != [f"D{index:02d}" for index in range(1, 9)]:
        raise ValueError("Development inputs must contain exactly D01 through D08")
    for case in cases:
        description = case.get("description")
        locations = case.get("source_paragraphs")
        if not isinstance(description, str) or not description.strip() or description not in paragraphs:
            raise ValueError(f"{case.get('case_id', 'unknown')} description is not an exact source paragraph")
        if not isinstance(locations, list) or not locations or any(
            not isinstance(location, int) or location < 1 or location > len(paragraphs)
            for location in locations
        ) or not any(paragraphs[location - 1] == description for location in locations):
            raise ValueError(f"{case['case_id']} source_paragraphs do not identify its exact description")
    return data, cases


def _final_case_blocks(source_text: str) -> list[dict]:
    """Parse organizer headings while preserving each enquiry's exact body text."""
    # Horizontal whitespace only: \\s would consume line endings and alter bodies.
    # Same-line enquiries require an explicit delimiter to avoid guessing titles.
    matches = list(re.finditer(
        r"(?m)^(?:\ufeff)?[ \t]*(H[0-9]{2})[ \t]*(?:(?P<delimiter>[:.)-|])[ \t]*(?P<inline>[^\r\n]*))?(?:\r?\n|$)",
        source_text,
    ))
    if not matches:
        raise ValueError("Final scenario source does not contain H01 through H06 headings")
    cases = []
    for index, match in enumerate(matches):
        case_id = match.group(1)
        start = match.end() if match.group("delimiter") == "|" else (
            match.start("inline") if match.group("inline") else match.end()
        )
        leading_separator = re.match(r"[ \t]*={10,}[ \t]*(?:\r?\n|$)", source_text[start:])
        if leading_separator:
            start += leading_separator.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
        # Boundary newlines separate heading blocks, not enquiry characters.
        while end > start and source_text[end - 1] in "\r\n":
            end -= 1
        block = source_text[start:end]
        separator = re.search(r"(?:\r?\n)[ \t]*={10,}[ \t]*$", block)
        if separator:
            end = start + separator.start()
            while end > start and source_text[end - 1] in "\r\n":
                end -= 1
        description = source_text[start:end]
        if not description.strip():
            raise ValueError(f"{case_id} has an empty enquiry")
        cases.append({"case_id": case_id, "description": description,
                      "source_span": [start, end],
                      "source_lines": [source_text.count("\n", 0, start) + 1,
                                       source_text.count("\n", 0, max(match.start(), end - 1)) + 1]})
    if [case["case_id"] for case in cases] != [f"H{n:02d}" for n in range(1, 7)]:
        raise ValueError("Final scenario source must contain exactly H01 through H06")
    return cases


def prepare_final_input(source_path: Path, output_path: Path = FINAL_INPUT) -> tuple[dict, list[dict]]:
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise ValueError(f"Original final scenario source is unavailable: {source_path}")
    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    cases = _final_case_blocks(source_text)
    data = {
        "schema_version": "f09-v1",
        "evaluation_kind": "final",
        "source_file": source_path.name,
        "source_path": str(source_path.relative_to(PROJECT_ROOT)) if source_path.is_relative_to(PROJECT_ROOT) else str(source_path),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_bytes": len(source_bytes),
        "cases": [{**case, "input_sha256": hashlib.sha256(case["description"].encode("utf-8")).hexdigest()}
                  for case in cases],
    }
    write_json(output_path, data)
    return data, data["cases"]


def load_final_cases(path: Path = FINAL_INPUT) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("evaluation_kind") != "final" or data.get("source_file") is None:
        raise ValueError("Final input must identify the organizer-provided source file")
    source_path = Path(data.get("source_path") or (SOURCE_ROOT / data["source_file"]))
    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path
    if not source_path.is_file():
        raise ValueError("Original final scenario source is unavailable")
    source_bytes = source_path.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != data.get("source_sha256"):
        raise ValueError("Final source hash does not match the prepared input")
    parsed = _final_case_blocks(source_bytes.decode("utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list) or [case.get("case_id") for case in cases] != [f"H{n:02d}" for n in range(1, 7)]:
        raise ValueError("Final inputs must contain exactly H01 through H06 in order")
    for expected, actual in zip(parsed, cases):
        if any(actual.get(key) != expected[key] for key in ("case_id", "description", "source_span", "source_lines")):
            raise ValueError(f"{actual.get('case_id', 'unknown')} text differs from the original source")
        if actual.get("input_sha256") != hashlib.sha256(actual["description"].encode("utf-8")).hexdigest():
            raise ValueError(f"{actual.get('case_id', 'unknown')} input hash is invalid")
    return data, cases


def git_identity() -> dict[str, str | bool | None]:
    def command(*args: str) -> str | None:
        try:
            result = subprocess.run(["git", "-c", "core.fsmonitor=false", *args], cwd=PROJECT_ROOT,
                                    capture_output=True, text=True, encoding="utf-8", check=True)
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    status = command("status", "--porcelain")
    return {"revision": command("rev-parse", "HEAD"), "working_tree_dirty": bool(status)}


def effective_settings(settings: Settings) -> dict:
    return {
        "provider_policy": settings.provider_name,
        "request_deadline_s": settings.request_deadline_s,
        "provider_call_timeout_s": settings.provider_call_timeout_s,
        "provider_max_retries": settings.provider_max_retries,
        "provider_max_completion_tokens": settings.provider_max_completion_tokens,
        "extraction_max_completion_tokens": settings.extraction_max_completion_tokens,
        "synthesis_max_completion_tokens": settings.synthesis_max_completion_tokens,
        "retrieval_semantic_min_score": settings.retrieval_semantic_min_score,
        "ingest_concurrency": settings.ingest_concurrency,
        "assessment_max_description_chars": settings.assessment_max_description_chars,
    }


def provider_profiles(settings: Settings) -> list[dict]:
    return [{"name":"dashscope", "enabled":True, "configured":settings.provider_configured,
             "model":settings.provider_model, "base_url":settings.provider_base_url}]


def execution_files() -> list[Path]:
    """Allowlist source and lockfiles, never .env, databases or source originals."""
    paths = [*PROJECT_ROOT.glob("backend/**/*.py"), *PROJECT_ROOT.glob("backend/prompts/**/*.txt"), *PROJECT_ROOT.glob("backend/templates/**/*.html"),
             *PROJECT_ROOT.glob("evaluation/*.py")]
    paths += [PROJECT_ROOT / name for name in ("requirements.txt", "frontend/package-lock.json")]
    return sorted(path for path in paths if path.is_file())


def configuration_record(settings: Settings) -> dict:
    current_pointer = settings.corpus_dir / "current.json"
    corpus_manifest = None
    index_manifest = None
    corpus_version = None
    if current_pointer.is_file():
        current = json.loads(current_pointer.read_text(encoding="utf-8"))
        directory = (settings.corpus_dir / current["directory"]).resolve()
        if not directory.is_relative_to(settings.corpus_dir.resolve()):
            raise ValueError("Corpus pointer escapes its configured directory")
        corpus_manifest = directory / "source_manifest.json"
        index_manifest = directory / "index_manifest.json"
        corpus_version = current["corpus_version"]
    return {
        "implementation_revision": git_identity()["revision"],
        "source_sha256": {path.relative_to(PROJECT_ROOT).as_posix(): file_hash(path) for path in execution_files()},
        "settings": effective_settings(settings),
        "provider_profiles": provider_profiles(settings),
        "pipeline_version": PIPELINE_VERSION,
        "prompt_versions": {"extraction": EXTRACTION_PROMPT_VERSION, "synthesis": SYNTHESIS_PROMPT_VERSION},
        "prompt_sha256": {"extraction": digest(EXTRACTION_PROMPT.encode()), "synthesis": digest(SYNTHESIS_PROMPT.encode())},
        "base_schema_sha256": {"extraction": digest(ExtractionOutput.model_json_schema()),
                               "synthesis": digest(SynthesisOutput.model_json_schema()),
                               "envelope": digest(AssessmentRun.model_json_schema())},
        "retrieval_version": RETRIEVAL_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "corpus_version": corpus_version,
        "corpus_manifest_sha256": file_hash(corpus_manifest) if corpus_manifest and corpus_manifest.is_file() else None,
        "index_manifest_sha256": file_hash(index_manifest) if index_manifest and index_manifest.is_file() else None,
        "policy": {"synthesis_temperature": 0.0, "content_repair_per_provider_per_stage": 1,
                   "max_evidence_records": 8, "max_followup_searches": 1,
                   "provider_cache": "none; single provider", "external_retrieval": False},
    }


def snapshot_configuration(batch_dir: Path, settings: Settings, configuration: dict) -> None:
    write_json(batch_dir / "configuration.json", configuration)
    for name, expected in configuration["source_sha256"].items():
        content = (PROJECT_ROOT / name).read_bytes()
        if digest(content) != expected:
            raise ValueError("Execution source changed while freezing configuration")
        atomic_bytes(batch_dir / "source_snapshot" / name, content)
    if configuration["corpus_version"]:
        pointer = json.loads((settings.corpus_dir / "current.json").read_text(encoding="utf-8"))
        directory = settings.corpus_dir / pointer["directory"]
        for name in ("source_manifest.json", "index_manifest.json"):
            atomic_bytes(batch_dir / "corpus" / name, (directory / name).read_bytes())


def audit_final_inputs(cases: list[dict], settings: Settings) -> dict:
    """Inspect runtime sources and eligible corpus text, excluding runner bookkeeping."""
    checked, findings = [], []
    snippets = [" ".join(case["description"].split()) for case in cases]
    paths = [path for path in execution_files() if path.is_relative_to(PROJECT_ROOT / "backend")]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        checked.append(path.relative_to(PROJECT_ROOT).as_posix())
        if re.search(r"\bH0[1-6]\b", text) or any(snippet in " ".join(text.split()) for snippet in snippets):
            findings.append(checked[-1])
    if (settings.corpus_dir / "current.json").is_file():
        from backend.services.search.evidence import load_snapshot
        snapshot = load_snapshot(settings.corpus_dir)
        for evidence_id, record in snapshot.records.items():
            text = " ".join(str(record.get("text", "")).split())
            if re.search(r"\bH0[1-6]\b", text) or any(snippet in text for snippet in snippets):
                findings.append(f"eligible evidence: {evidence_id}")
        checked.append(f"eligible corpus records: {snapshot.version}")
    if findings:
        raise ValueError("Final-case content found in runtime sources or eligible evidence: " + ", ".join(findings))
    return {"scope": "runtime code/prompts and eligible corpus text; not proof against arbitrary semantic lookups",
            "checked": checked, "findings": findings}


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _safe_case_record(case: dict, output: AssessmentRun | None, *, status: int | None,
                      elapsed_s: float, error: str | None = None) -> dict:
    payload = output.model_dump(mode="json") if output is not None else None
    metadata = payload.get("metadata", {}) if payload else {}
    first_error = (payload.get("errors") or [None])[0] if payload else None
    return {
        "case_id": case["case_id"],
        "input_sha256": hashlib.sha256(case["description"].encode("utf-8")).hexdigest(),
        "http_status": status,
        "run_status": payload.get("run_status") if payload else None,
        "decision_status": (payload.get("assessment") or {}).get("decision_status") if payload else None,
        "outcome": "complete" if payload and payload.get("run_status") == "complete" else "incomplete",
        "run_id": metadata.get("run_id"),
        "enquiry_id": metadata.get("enquiry_id"),
        "stage_providers": metadata.get("stage_providers", {}),
        "provider_attempts": metadata.get("provider_attempts", []),
        "returned_models": metadata.get("returned_models", {}),
        "schema_sha256": metadata.get("schema_sha256", {}),
        "repair_counts": metadata.get("repair_counts", {}),
        "elapsed_s": elapsed_s,
        "error": error or first_error,
    }


def build_review(batch_dir: Path, manifest: dict) -> dict:
    """Create a review receipt without pretending membership proves entailment."""
    cases = []
    for record in manifest["cases"]:
        output_path = record.get("output_path")
        assessment_run = None
        if output_path:
            assessment_run = AssessmentRun.model_validate_json((batch_dir / output_path).read_bytes())
        assessment = assessment_run.assessment if assessment_run else None
        retrieval = assessment_run.retrieval if assessment_run else None
        citations = [source.model_dump(mode="json") for source in assessment.source_index] if assessment else []
        questions = [question.question for question in assessment.clarification_questions] if assessment else []
        experiment = assessment.experiment if assessment else None
        cases.append({
            "case_id": record["case_id"],
            "run_id": record.get("run_id"),
            "run_status": record.get("run_status"),
            "decision_status": record.get("decision_status"),
            "cited_sources": citations,
            "retrieved_evidence_count": len(retrieval.evidence) if retrieval else 0,
            "critical_missing_questions": questions,
            "independent_validation": {
                "proposed": bool(experiment and experiment.validation),
                "validation_groups": [group.model_dump(mode="json") for group in experiment.validation_groups] if experiment else [],
            },
            "claim_support_review": {
                "mechanical_reference_check": "passed by validated API" if assessment_run and not assessment_run.errors else "not available",
                "method_rationale_consistency": "passed by validated API" if assessment_run and not assessment_run.errors else "not available",
                "semantic_source_entailment": "unreviewed",
                "unsupported_claim_count": None,
                "reviewer_type": "automated boundary inspection; independent scientific review not performed",
            },
            "residual_limitations": [
                "Citation membership and source excerpts do not establish arbitrary scientific entailment.",
                "Saved results are provisional and do not establish spectroscopy performance.",
            ],
        })
    return {
        "batch_id": manifest["batch_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_scope": "development output inventory and mechanical provenance; semantic support remains explicitly reviewable",
        "cases": cases,
    }


async def run_cases(settings: Settings, *, selected: set[str] | None = None,
                    input_path: Path = DEVELOPMENT_INPUT, output_dir: Path = DEFAULT_OUTPUT,
                    evaluation_kind: str = "development") -> tuple[dict, int]:
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    if evaluation_kind not in {"development", "final"}:
        raise ValueError("Unknown evaluation suite")
    source_data, cases = (load_final_cases(input_path) if evaluation_kind == "final"
                          else load_development_cases(input_path))
    selected = {case["case_id"] for case in cases} if selected is None else selected
    known = {case["case_id"] for case in cases}
    if not selected or selected - known:
        raise ValueError("Select existing development cases")
    if evaluation_kind == "final" and selected != FINAL_CASE_IDS:
        raise ValueError("Final evaluation always runs all H01-H06 cases")

    batch_id = uuid4().hex
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = output_dir / f"{stamp}_{batch_id}"
    history_path = batch_dir / "explainability.sqlite"
    run_settings = settings.model_copy(update={"explainability_db_path": history_path})
    audit = audit_final_inputs(cases, run_settings) if evaluation_kind == "final" else None
    frozen_configuration = configuration_record(run_settings)
    batch_dir.mkdir(parents=True, exist_ok=False)
    snapshot_configuration(batch_dir, run_settings, frozen_configuration)
    atomic_bytes(batch_dir / "inputs.json", input_path.read_bytes())
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_kind": evaluation_kind,
        "input_file": "inputs.json",
        "input_file_sha256": file_hash(input_path),
        "source_file": source_data["source_file"],
        "source_sha256": source_data["source_sha256"],
        "selected_cases": sorted(selected),
        "implementation": git_identity(),
        "pipeline_version": PIPELINE_VERSION,
        "prompt_versions": {"extraction": EXTRACTION_PROMPT_VERSION, "synthesis": SYNTHESIS_PROMPT_VERSION},
        "prompt_sha256": {"extraction": digest(EXTRACTION_PROMPT.encode()), "synthesis": digest(SYNTHESIS_PROMPT.encode())},
        "schema_sha256": {"extraction": digest(ExtractionOutput.model_json_schema()), "synthesis": digest(SynthesisOutput.model_json_schema())},
        "settings": effective_settings(run_settings),
        "provider_profiles": provider_profiles(run_settings),
        "configuration": frozen_configuration,
        "configuration_id": digest(frozen_configuration),
        "history_db": "explainability.sqlite",
        "case_audit": audit,
        "cases": [],
        "review_status": "pending_source_support_inspection",
    }
    write_json(batch_dir / "manifest.json", manifest)
    application = create_app(run_settings)
    failed = False

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://evaluation.local") as client:
        for case in cases:
            if case["case_id"] not in selected:
                continue
            if (configuration_record(run_settings) != frozen_configuration
                    or file_hash(input_path) != manifest["input_file_sha256"]):
                manifest["configuration_drift"] = True
                failed = True
                break
            if evaluation_kind == "final":
                load_final_cases(input_path)
            started = time.monotonic()
            started_at = datetime.now(timezone.utc).isoformat()
            # Keep each case's provider health/cache independent. A malformed
            # response must not suppress otherwise valid later cases, while all
            # cases still share the isolated history database and settings.
            request_path = batch_dir / f"{case['case_id']}.request.json"
            write_json(request_path, {"description": case["description"]})
            response = None
            output = None
            error = None
            try:
                response = await client.post("/api/assess", json={"description": case["description"]})
                if response.status_code in {200, 502, 503, 504}:
                    output = AssessmentRun.model_validate(response.json())
                else:
                    error = f"HTTP {response.status_code}: assessment envelope was not returned"
            except (httpx.HTTPError, ValueError) as caught:
                error = type(caught).__name__
            elapsed = time.monotonic() - started
            case_record = _safe_case_record(case, output, status=response.status_code if response else None,
                                            elapsed_s=elapsed, error=error)
            case_record.update(configuration_id=manifest["configuration_id"], started_at=started_at,
                               completed_at=datetime.now(timezone.utc).isoformat())
            case_record["source_locations"] = case.get("source_paragraphs") or case.get("source_lines")
            case_record["request_path"] = request_path.name
            case_record["request_sha256"] = file_hash(request_path)
            envelope_path = batch_dir / f"{case['case_id']}.json"
            if output is not None:
                atomic_bytes(envelope_path, response.content)
                run_id = output.metadata.run_id
                case_record["export_errors"] = []
                for suffix, route in (("trace.json", f"/api/assess/{run_id}/explainability"),
                                      ("trace.pdf", f"/api/assess/{run_id}/report.pdf?audience=trace")):
                    try:
                        export_response = await client.get(route)
                        if export_response.status_code != 200:
                            raise ValueError(f"HTTP {export_response.status_code}")
                        if suffix == "trace.json":
                            export_response.json()
                        elif not export_response.content.startswith(b"%PDF"):
                            raise ValueError("Invalid PDF response")
                        export_path = batch_dir / f"{case['case_id']}.{suffix}"
                        atomic_bytes(export_path, export_response.content)
                        prefix = "trace" if suffix == "trace.json" else "trace_pdf"
                        case_record[f"{prefix}_path"] = export_path.name
                        case_record[f"{prefix}_sha256"] = file_hash(export_path)
                    except (httpx.HTTPError, ValueError, OSError) as caught:
                        case_record["export_errors"].append(f"{suffix}: {type(caught).__name__}")
                evidence_path = batch_dir / f"{case['case_id']}.evidence.json"
                write_json(evidence_path, [entry.model_dump(mode="json") for entry in (output.retrieval.evidence if output.retrieval else [])])
                case_record["evidence_path"] = evidence_path.name
                case_record["evidence_sha256"] = file_hash(evidence_path)
                if not case_record.get("trace_path"):
                    failed = True
            else:
                raw_path = batch_dir / f"{case['case_id']}.http.json"
                atomic_bytes(raw_path, response.content if response is not None else b"null")
                case_record["http_response_path"] = raw_path.name
                failed = True
            if case_record["outcome"] != "complete":
                failed = True
            case_record["output_path"] = envelope_path.name if output is not None else None
            if output is not None:
                case_record["output_sha256"] = file_hash(envelope_path)
            manifest["cases"].append(case_record)
            write_json(batch_dir / "manifest.json", manifest)

    if configuration_record(run_settings) != frozen_configuration or file_hash(input_path) != manifest["input_file_sha256"]:
        manifest["configuration_drift"] = True
        failed = True
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest["review_status"] = "pending_source_support_inspection"
    manifest["all_selected_cases_complete"] = not failed
    review_path = batch_dir / "review.json"
    write_json(review_path, build_review(batch_dir, manifest))
    manifest["review_path"] = review_path.name
    write_json(batch_dir / "manifest.json", manifest)
    return manifest, int(failed)


def artifact_path(base: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("Artifact path must be relative to its batch")
    path = (base / name).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("Artifact path escapes its batch")
    return path


def checked_artifact(base: Path, name: str, expected_hash: str) -> bytes:
    content = artifact_path(base, name).read_bytes()
    if not expected_hash or digest(content) != expected_hash:
        raise ValueError(f"Artifact hash mismatch: {name}")
    return content


def verify_manifest(manifest_path: Path, *, require_complete: bool = True) -> tuple[dict, list[str]]:
    """Verify a portable batch without its originals, live corpus, provider or SQLite."""
    manifest_path = manifest_path.resolve()
    base = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if "published_from" in manifest:
        original_path = artifact_path(base, manifest["published_from"])
        original = json.loads(original_path.read_bytes())
        if "published_from" in original or original_path == manifest_path:
            return manifest, ["Published manifest must reference an original batch"]
        _, errors = verify_manifest(original_path, require_complete=True)
        if any(manifest.get(key) != value for key, value in original.items()):
            errors.append("Published manifest differs from its original batch")
        for record in original.get("cases", []):
            try:
                checked_artifact(base, f"{record['case_id']}.json", record["output_sha256"])
            except (OSError, ValueError, KeyError) as caught:
                errors.append(f"Published output: {caught}")
        return manifest, errors
    if manifest.get("schema_version") != MANIFEST_VERSION:
        return manifest, ["Unsupported manifest version; legacy batches cannot be published"]
    final = manifest.get("evaluation_kind") == "final"
    require_complete = require_complete or final
    configuration = manifest.get("configuration", {})
    identity = digest(configuration)
    if manifest.get("configuration_id") != identity or manifest.get("configuration_drift"):
        errors.append("configuration identity is invalid or drift was detected")
    if require_complete and (not manifest.get("all_selected_cases_complete") or not manifest.get("completed_at")):
        errors.append("batch did not finish completely")
    try:
        frozen = json.loads((base / "configuration.json").read_bytes())
        if frozen != configuration:
            raise ValueError("Frozen configuration differs from manifest")
        for name, expected_hash in configuration["source_sha256"].items():
            checked_artifact(base / "source_snapshot", name, expected_hash)
        for name, key in (("source_manifest.json", "corpus_manifest_sha256"),
                          ("index_manifest.json", "index_manifest_sha256")):
            if configuration.get(key):
                checked_artifact(base / "corpus", name, configuration[key])
        input_bytes = checked_artifact(base, manifest["input_file"], manifest["input_file_sha256"])
        source = json.loads(input_bytes)
        if source["source_sha256"] != manifest["source_sha256"]:
            raise ValueError("Original-source identity differs from input snapshot")
        inputs = {case["case_id"]: case["description"] for case in source["cases"]}
        input_ids = [case["case_id"] for case in source["cases"]]
        if len(inputs) != len(input_ids):
            raise ValueError("Duplicate input IDs")
        if final and set(input_ids) != FINAL_CASE_IDS:
            raise ValueError("Final input snapshot must contain H01-H06")
    except (OSError, ValueError, KeyError, TypeError) as caught:
        return manifest, errors + [f"Invalid frozen artifacts: {caught}"]
    expected = FINAL_CASE_IDS if final else set(manifest.get("selected_cases", []))
    records = manifest.get("cases", [])
    if (not expected or len(records) != len(expected)
            or {record.get("case_id") for record in records} != expected
            or set(manifest.get("selected_cases", [])) != expected):
        errors.append("manifest case set does not match the selected suite, or contains duplicates")
    run_ids, enquiry_ids = set(), set()
    for record in records:
        case_id = record.get("case_id")
        try:
            if record.get("configuration_id") != identity:
                raise ValueError("case belongs to another configuration")
            if record.get("output_path") != f"{case_id}.json":
                raise ValueError("output path must identify this batch's case")
            description = inputs[case_id]
            if digest(description.encode("utf-8")) != record.get("input_sha256"):
                raise ValueError("input hash differs from frozen original enquiry")
            request = json.loads(checked_artifact(base, record["request_path"], record["request_sha256"]))
            if request != {"description": description}:
                raise ValueError("request changes the original enquiry or adds history/clarifications")
            envelope = AssessmentRun.model_validate_json(checked_artifact(base, record["output_path"], record["output_sha256"]))
            metadata = envelope.metadata.model_dump(mode="json")
            for key in ("run_id", "enquiry_id", "stage_providers", "provider_attempts", "returned_models",
                        "schema_sha256", "repair_counts"):
                if metadata[key] != record.get(key):
                    raise ValueError(f"manifest {key} differs from envelope")
            if metadata["run_id"] in run_ids or metadata["enquiry_id"] in enquiry_ids:
                raise ValueError("initial cases reuse a run or enquiry ID")
            run_ids.add(metadata["run_id"])
            enquiry_ids.add(metadata["enquiry_id"])
            if metadata["parent_run_id"] is not None or metadata["round_no"] != 1:
                raise ValueError("initial enquiry contains continuation history")
            if (envelope.run_status != record.get("run_status")
                    or (envelope.assessment.decision_status if envelope.assessment else None) != record.get("decision_status")
                    or record.get("outcome") != ("complete" if envelope.run_status == "complete" else "incomplete")):
                raise ValueError("manifest run/scientific outcomes differ from envelope")
            if require_complete and (envelope.run_status != "complete" or record.get("http_status") != 200):
                raise ValueError("run is not complete with HTTP 200")
            for key in ("pipeline_version", "prompt_versions", "prompt_sha256"):
                if metadata[key] != configuration[key]:
                    raise ValueError(f"{key} differs from frozen configuration")
            limits = configuration["settings"]
            for key, expected_value in {
                "provider_mode": limits["provider_policy"],
                "call_timeout_s": limits["provider_call_timeout_s"],
                "request_deadline_s": limits["request_deadline_s"],
                "provider_max_retries": limits["provider_max_retries"],
                "provider_max_completion_tokens": limits["provider_max_completion_tokens"],
                "extraction_max_completion_tokens": min(limits["extraction_max_completion_tokens"], limits["provider_max_completion_tokens"]),
                "synthesis_max_completion_tokens": min(limits["synthesis_max_completion_tokens"], limits["provider_max_completion_tokens"]),
            }.items():
                if metadata[key] != expected_value:
                    raise ValueError(f"{key} differs from frozen settings")
            profiles = {profile["name"]: profile for profile in configuration["provider_profiles"]}
            for stage, actual in metadata["stage_providers"].items():
                profile = profiles[actual["provider"]]
                if (not profile["enabled"] or not profile["configured"] or actual["model"] != profile["model"]
                        or actual["endpoint"] != profile["base_url"]):
                    raise ValueError(f"{stage} provider differs from frozen profile")
            if require_complete and set(metadata["stage_providers"]) != {"extraction", "synthesis"}:
                raise ValueError("actual stage identities are missing")
            if envelope.facts:
                validate_extraction(envelope.facts, description)
            exported = json.loads(checked_artifact(base, record["evidence_path"], record["evidence_sha256"]))
            ledger = [entry.model_dump(mode="json") for entry in envelope.retrieval.evidence] if envelope.retrieval else []
            if exported != ledger:
                raise ValueError("portable evidence differs from envelope ledger")
            if envelope.retrieval:
                if envelope.retrieval.corpus_version != configuration["corpus_version"]:
                    raise ValueError("corpus version differs from frozen configuration")
                if envelope.retrieval.retrieval_version != configuration["retrieval_version"]:
                    raise ValueError("retrieval version differs from frozen configuration")
                _check_synthesis_inputs(envelope.facts, envelope.retrieval)
            if envelope.assessment:
                validate_final(envelope.assessment, envelope.facts, envelope.retrieval)
            trace = json.loads(checked_artifact(base, record["trace_path"], record["trace_sha256"]))
            if (trace["run_id"] != metadata["run_id"] or trace["enquiry_id"] != metadata["enquiry_id"]
                    or trace["description"] != description or trace.get("clarification_answers")
                    or trace.get("parent_run_id") is not None or trace["round_no"] != 1):
                raise ValueError("trace identity/input differs from initial run")
            trace_run = trace["run"]
            trace_run["metadata"]["provider_trace"] = []
            if trace_run != envelope.model_dump(mode="json"):
                raise ValueError("trace result differs from envelope")
        except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration) as caught:
            errors.append(f"{case_id}: {caught}")
    return manifest, errors


def publish_batch(manifest_path: Path) -> tuple[dict, int]:
    manifest_path = manifest_path.resolve()
    manifest, errors = verify_manifest(manifest_path)
    if errors:
        return {"errors": errors}, 1
    if manifest.get("evaluation_kind") != "final":
        return {"errors": ["only a final batch can be published"]}, 1
    output_dir = PROJECT_ROOT / "outputs"
    if not manifest_path.is_relative_to(output_dir):
        return {"errors": ["Publication requires a batch under the repository outputs directory"]}, 1
    if "published_from" in manifest:
        return {"errors": ["Publish an original batch, not the canonical manifest"]}, 1
    for candidate in manifest_path.parent.parent.glob("*/manifest.json"):
        if candidate.resolve() == manifest_path:
            continue
        try:
            earlier = json.loads(candidate.read_bytes())
        except (OSError, ValueError):
            continue
        if (earlier.get("configuration_id") == manifest["configuration_id"]
                and earlier.get("evaluation_kind") == "final"
                and earlier.get("all_selected_cases_complete")
                and earlier.get("completed_at", "~") < manifest["completed_at"]):
            _, earlier_errors = verify_manifest(candidate)
            if not earlier_errors:
                return {"errors": ["Publish the first complete verified batch under this configuration"]}, 1
    # A final set is copied as a unit. Preserve any earlier canonical set and
    # restore it if publication fails before the new manifest is installed.
    targets = [output_dir / f"{case_id}.json" for case_id in sorted(FINAL_CASE_IDS)] + [output_dir / "run_manifest.json"]
    previous = {path: path.read_bytes() if path.exists() else None for path in targets}
    if any(content is not None for content in previous.values()):
        archive = output_dir / "runs" / f"previous_submission_{uuid4().hex}"
        for path, content in previous.items():
            if content is not None:
                atomic_bytes(archive / path.name, content)
    published = {**manifest, "published_at": datetime.now(timezone.utc).isoformat(),
                 "published_from": manifest_path.relative_to(output_dir).as_posix(),
                 "canonical_outputs": {record["case_id"]: f"{record['case_id']}.json" for record in manifest["cases"]}}
    try:
        for record in manifest["cases"]:
            content = checked_artifact(manifest_path.parent, record["output_path"], record["output_sha256"])
            atomic_bytes(output_dir / f"{record['case_id']}.json", content)
        write_json(output_dir / "run_manifest.json", published)
    except (OSError, ValueError):
        for path, content in previous.items():
            if content is not None:
                atomic_bytes(path, content)
            elif path.exists():
                path.unlink()
        raise
    return published, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", dest="cases", help="Development case ID; repeatable; defaults to D01-D08")
    parser.add_argument("--suite", choices=["development", "final"], default="development")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--prepare-final", action="store_true", help="Prepare evaluation/final.json from the original H01-H06 source")
    actions.add_argument("--verify", type=Path, help="Verify a saved batch manifest without model calls")
    actions.add_argument("--publish", type=Path, help="Verify and publish a complete final batch")
    parser.add_argument("--source", type=Path, help="Original final scenario source for --prepare-final")
    parser.add_argument("--request-deadline-s", type=float, default=90)
    parser.add_argument("--call-timeout-s", type=float, default=30)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.prepare_final:
        source = (args.source or (SOURCE_ROOT / "customer_scenarios_for_final_evaluation.txt"))
        try:
            data, cases = prepare_final_input(source)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            parser.error(f"Final input could not be prepared: {type(error).__name__}: {error}")
        print(json.dumps({"source_sha256": data["source_sha256"], "cases": [case["case_id"] for case in cases]}, indent=2))
        return 0
    if args.verify:
        try:
            manifest, errors = verify_manifest(args.verify, require_complete=True)
        except (OSError, ValueError, KeyError, TypeError) as caught:
            parser.error(f"Cannot verify batch: {caught}")
        print(json.dumps({"batch_id": manifest.get("batch_id"), "valid": not errors, "errors": errors}, indent=2))
        return int(bool(errors))
    if args.publish:
        try:
            manifest, code = publish_batch(args.publish)
        except (OSError, ValueError, KeyError, TypeError) as caught:
            parser.error(f"Cannot publish batch: {caught}")
        print(json.dumps({"batch_id": manifest.get("batch_id"), "published": code == 0, "errors": manifest.get("errors", [])}, indent=2))
        return code
    settings = Settings()
    settings = Settings(_env_file=None, **{**settings.model_dump(),
                                           "request_deadline_s": args.request_deadline_s,
                                           "provider_call_timeout_s": args.call_timeout_s})
    if args.suite == "final" and args.cases:
        parser.error("Final evaluation always runs all H01-H06 cases")
    input_path = args.input or (FINAL_INPUT if args.suite == "final" else DEVELOPMENT_INPUT)
    output_dir = args.output_dir or (FINAL_OUTPUT if args.suite == "final" else DEFAULT_OUTPUT)
    try:
        manifest, code = asyncio.run(run_cases(settings, selected=set(args.cases) if args.cases else None,
                                                input_path=input_path, output_dir=output_dir,
                                                evaluation_kind=args.suite))
    except (OSError, ValueError, KeyError, CorpusUnavailable) as error:
        parser.error(f"Evaluation could not start: {type(error).__name__}: {error}")
    print(json.dumps({"batch_id": manifest["batch_id"], "cases": len(manifest["cases"]),
                      "all_selected_cases_complete": manifest["all_selected_cases_complete"]}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
