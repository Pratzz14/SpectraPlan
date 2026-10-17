"""Reproducible source ingestion: python -m backend.ingest build|validate|report|search|pilot."""

import argparse
import asyncio
import base64
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.config import Settings
from backend.knowledge_models import EXTRACTOR_VERSION, SCHEMA_VERSION, PageExtraction, PageVerification
from backend.knowledge_report import render_report
from backend.knowledge_store import (MISSING_OPTIONAL, active_directory, canonical_candidate, digest, extract_pages,
                                     file_hash, import_methods, inventory, load_records, publish, read_json,
                                     validate_corpus, write_json)
from backend.provider import Provider, ProviderError

PROMPTS = Path(__file__).with_name("prompts")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def extraction_config(settings: Settings) -> Settings:
    # A corpus build is many independent page jobs, not one interactive request.
    return settings.model_copy(update={"provider_call_timeout_s": max(90, settings.provider_call_timeout_s),
                                       "request_deadline_s": max(240, settings.request_deadline_s),
                                       "provider_reasoning_effort": "none"})


def pipeline_fingerprint(config: Settings) -> dict:
    return {"schema": SCHEMA_VERSION, "extractor": EXTRACTOR_VERSION,
            "pymupdf": __import__("pymupdf").VersionBind,
            "extract_prompt_sha256": file_hash(PROMPTS / "knowledge_extract.txt"),
            "verify_prompt_sha256": file_hash(PROMPTS / "knowledge_verify.txt"),
            "schema_sha256": digest([PageExtraction.model_json_schema(), PageVerification.model_json_schema()]),
            "extraction_schema_sha256": digest(PageExtraction.model_json_schema()),
            "verification_schema_sha256": digest(PageVerification.model_json_schema()),
            "model": config.provider_model, "endpoint": config.provider_base_url,
            "provider": config.provider_name,
            "reasoning_effort": config.provider_reasoning_effort, "max_completion_tokens": config.ingest_max_output_tokens,
            "call_timeout_s": config.provider_call_timeout_s, "deadline_s": config.request_deadline_s,
            "max_retries": config.provider_max_retries}


def page_messages(page: dict, directory: Path, system: str, extra: str = "", *, include_image=None) -> list[dict]:
    header = {"source_id": page["source_id"], "file_name": page["file_name"], "source_role": page["role"],
              "physical_pdf_page_1_based": page["page"],
              "blocks": [{"block_id": b["block_id"], "text": b["text"]} for b in page["blocks"]],
              "image_coordinate_system": "relative coordinates from 0 to 1"}
    content = [{"type": "text", "text": json.dumps(header, ensure_ascii=False) + extra}]
    send_image = page.get("needs_vision", True) if include_image is None else include_image
    if send_image:
        image_bytes = (directory / page["image"]).read_bytes()
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()}})
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


class IngestionTransport:
    """Long-running ingestion can wait for token replenishment; interactive calls cannot."""
    def __init__(self, settings):
        self.provider = Provider(extraction_config(settings))
        self.fatal = None
        self.next_request_at = 0.0

    async def structured(self, *args, **kwargs):
        if self.fatal:
            raise self.fatal
        generation_retries = 0
        for attempt in range(6):
            try:
                while time.monotonic() < self.next_request_at:
                    await asyncio.sleep(min(60, self.next_request_at - time.monotonic()))
                result = await self.provider.structured(*args, **kwargs)
                usage = self.provider.last_usage
                # Account-specific defaults verified from Groq's rejection messages.
                if self.provider.settings.provider_name == "groq":
                    self.next_request_at = time.monotonic() + max(usage.get("prompt_tokens", 0) / 7000,
                                                                  usage.get("completion_tokens", 0) / 1000) * 60
                return result
            except ProviderError as error:
                if error.daily_limit or error.code in {"provider_authentication", "provider_not_configured"}:
                    self.fatal = error
                    raise
                if error.upstream_code == "json_validate_failed" and generation_retries < 1 and attempt < 5:
                    generation_retries += 1
                    print("Qwen returned incomplete structured JSON; retrying this stage once after token refill (no content repair).", flush=True)
                    await asyncio.sleep(60)
                    continue
                if error.upstream_status != 429 or attempt == 5:
                    raise
                delay = 2 if self.provider.settings.provider_name == "llmtech" else 60
                print(f"Provider rate limit; waiting {delay} seconds before resuming this stage.", flush=True)
                await asyncio.sleep(delay)


def empty_omits_substantive(extraction: PageExtraction, page: dict) -> bool:
    if extraction.candidates or sum(len(b["text"]) for b in page["blocks"]) <= 300:
        return False
    reason = (extraction.empty_reason or "").casefold()
    raw = " ".join(b["text"] for b in page["blocks"]).casefold()
    # Continuation bibliography pages may have no repeated "References" heading.
    body = []
    for block in page["blocks"]:
        # Normalize typography only for classifying back matter; source text stays untouched.
        text = unicodedata.normalize("NFKC", block["text"]).strip()
        if (not text or re.search(r"\b\d+ of \d+\b", text)
                or text.startswith("Analytical Chemistry\npubs.acs.org/ac\n")
                or re.match(r"^(?:Acknowledg(?:e)?ments|Author Contributions|Conflicts of Interest):", text)):
            continue
        body.append(text)
    starts_bibliography = bool(body and re.match(r"^(?:References\b|Bibliography\b|\(?\d+[.)]\s*[A-Z])", body[0]))
    bibliography = ("reference" in reason or "bibliograph" in reason) and starts_bibliography
    legal_page = (any(b["text"].strip().casefold().startswith("disclaimer") for b in page["blocks"][:2])
                  and "copyright" in raw and "general informational purposes" in raw
                  and any(word in reason for word in ("legal", "disclaimer", "copyright")))
    return not (bibliography or legal_page)


def deduplicate_records(records: list[dict]) -> list[dict]:
    """Keep the best validated annotation when Qwen selects identical source spans twice."""
    grouped = {}
    for record in records:
        grouped.setdefault(record["evidence_id"], []).append(record)
    result = []
    for variants in grouped.values():
        best = max(variants, key=lambda r: (r["retrieval_eligible"], r["validation_status"] == "passed", -len(r["issues"])))
        if len(variants) > 1:
            best = dict(best)
            best["alternative_annotations"] = [{k: r[k] for k in ("section", "facts", "verification", "issues", "revision")}
                                               for r in variants if r is not best and r != best]
            best["revision"] = digest({"selected": best["revision"], "alternatives": best["alternative_annotations"]})[:24]
        result.append(best)
    return result


def apply_source_checks(records: list[dict], checks: list[dict], pages: list[dict]) -> None:
    """Apply reproducible project inspection exclusions without implying human/AFS approval."""
    by_id = {r["evidence_id"]: r for r in records}
    page_hashes = {(p["source_id"], p["page"]): p["image_sha256"] for p in pages}
    for check in checks:
        record = by_id.get(check["evidence_id"])
        if record is None:
            continue  # A changed extraction may no longer contain this candidate.
        if record["source_sha256"] != check["source_sha256"] or page_hashes[(record["source_id"], record["page"])] != check["image_sha256"]:
            raise ValueError("Project source check no longer matches original source bytes")
        record["project_source_check"] = check
        record["issues"] = sorted(set(record["issues"] + ["Project source inspection: " + check["reason"]]))
        record["validation_status"] = "flagged"
        record["retrieval_eligible"] = False
        record["revision"] = digest({"original": record["revision"], "source_check": check})[:24]


async def process_page(page: dict, directory: Path, settings: Settings, fingerprint: dict,
                       semaphore: asyncio.Semaphore, refresh: bool, provider=None) -> tuple[list[dict], dict]:
    input_data = {"source_sha256": page["source_sha256"], "page": page["page"],
                  "image_sha256": page["image_sha256"], "needs_vision": page.get("needs_vision", True),
                  "blocks": page["blocks"]}
    key = digest({**input_data, "pipeline": fingerprint})
    extraction_pipeline = {k: v for k, v in fingerprint.items() if k not in {"verify_prompt_sha256", "verification_schema_sha256", "schema_sha256"}}
    extraction_key = digest({**input_data, "pipeline": extraction_pipeline})
    cache_file = settings.ingest_cache_dir / f"{key}.json"
    async with semaphore:
        if cache_file.exists() and not refresh:
            bundle = read_json(cache_file)
            if bundle["input_key"] != key:
                raise ValueError("Extraction cache fingerprint mismatch")
            extraction = PageExtraction.model_validate(bundle["extraction"])
            verification = PageVerification.model_validate(bundle["verification"])
            cached = True
        else:
            transport = provider or IngestionTransport(settings)
            partial_file = settings.ingest_cache_dir / f"{extraction_key}.extraction.json"
            # Reuse an actual prior response when only the verification contract changed.
            # Its original request fingerprint is preserved; source identity is checked by recomputing its key.
            if not partial_file.exists() and not refresh:
                for previous_file in settings.ingest_cache_dir.glob("*.json"):
                    if previous_file.name.endswith(".extraction.json"):
                        continue
                    previous = read_json(previous_file)
                    old_pipeline = previous.get("pipeline", {})
                    comparable = {"schema", "extractor", "pymupdf", "extract_prompt_sha256", "model", "endpoint", "reasoning_effort", "max_completion_tokens"}
                    if any(old_pipeline.get(k) != fingerprint.get(k) for k in comparable):
                        continue
                    if previous_file.stem != digest({**input_data, "pipeline": old_pipeline}):
                        continue
                    prior = PageExtraction.model_validate(previous["extraction"])
                    write_json(partial_file, {"input_key": extraction_key, "origin_pipeline": old_pipeline,
                               "origin_cache": previous_file.name, "extraction": prior.model_dump()})
                    break
            if partial_file.exists() and not refresh:
                partial = read_json(partial_file)
                if partial["input_key"] != extraction_key:
                    raise ValueError("Partial extraction cache fingerprint mismatch")
                extraction = PageExtraction.model_validate(partial["extraction"])
                if empty_omits_substantive(extraction, page):
                    # An invalid empty partial is inspectable but must not poison resumed builds.
                    partial_file.replace(partial_file.with_suffix(".rejected"))
                    extraction = None
            else:
                extraction = None
            if extraction is None:
                if file_hash(PROMPTS / "knowledge_extract.txt") != fingerprint["extract_prompt_sha256"]:
                    raise ValueError("Extraction prompt changed during build; restart to preserve provenance")
                extraction = await transport.structured(page_messages(page, directory,
                    (PROMPTS / "knowledge_extract.txt").read_text(encoding="utf-8")), PageExtraction,
                    max_completion_tokens=settings.ingest_max_output_tokens)
                write_json(partial_file, {"input_key": extraction_key, "extraction": extraction.model_dump()})
            if not extraction.candidates and not extraction.empty_reason:
                raise ValueError("Empty model extraction has no explanation")
            if empty_omits_substantive(extraction, page):
                raise ValueError("Model omitted a substantive page; empty result held back")
            if extraction.candidates:
                if file_hash(PROMPTS / "knowledge_verify.txt") != fingerprint["verify_prompt_sha256"]:
                    raise ValueError("Verification prompt changed during build; restart to preserve provenance")
                numbered = [{"candidate_index": i, "candidate": c.model_dump()} for i, c in enumerate(extraction.candidates)]
                verification = await transport.structured(page_messages(page, directory,
                    (PROMPTS / "knowledge_verify.txt").read_text(encoding="utf-8"),
                    "\nCandidates to check:\n" + json.dumps(numbered, ensure_ascii=False),
                    include_image=bool(extraction.figures)), PageVerification,
                    max_completion_tokens=min(2048 if settings.provider_name == "llmtech" else 768, settings.ingest_max_output_tokens))
            else:
                verification = PageVerification(verdicts=[])
            bundle = {"input_key": key, "pipeline": fingerprint, "created_at": utc_now(),
                      "extraction": extraction.model_dump(), "verification": verification.model_dump()}
            write_json(cache_file, bundle)
            cached = False
        indices = [v.candidate_index for v in verification.verdicts]
        if empty_omits_substantive(extraction, page):
            raise ValueError("Cached model result omitted a substantive page; rerun with --refresh")
        if sorted(indices) != list(range(len(extraction.candidates))):
            raise ValueError("Verification must return exactly one verdict per candidate")
        verdicts = {v.candidate_index: v.model_dump() for v in verification.verdicts}
        revision = digest({"input_key": key, "output": bundle["extraction"], "verification": bundle["verification"]})
        records = [canonical_candidate(c, page, verdicts[i], revision) for i, c in enumerate(extraction.candidates)]
        # Identical selections on a page are one evidence record, never duplicate IDs.
        records = deduplicate_records(records)
        coverage = {"source_id": page["source_id"], "page": page["page"], "status": "processed",
                    "extraction_key": key, "records": len(records),
                    "eligible": sum(r["retrieval_eligible"] for r in records), "empty_reason": extraction.empty_reason,
                    "issues": extraction.issues, "automated_review_only": True}
        print(f"{page['source_id']} p.{page['page']}: {len(records)} records, {coverage['eligible']} eligible ({'cached' if cached else 'Qwen'})", flush=True)
        return records, coverage


async def build(settings: Settings, *, refresh=False, pilot=False) -> Path:
    from backend.retrieval import Embedder, build_indexes

    sources = inventory(settings.source_dir)
    config = extraction_config(settings)
    fingerprint = pipeline_fingerprint(config)
    root = settings.corpus_dir
    staged = root / ".staging" / uuid4().hex
    staged.mkdir(parents=True)
    write_json(staged / "build_status.json", {"started_at": utc_now(), "status": "running", "pipeline": fingerprint})
    try:
        pages = extract_pages(settings.source_dir, sources, staged)
        write_json(staged / "raw_pages.json", pages)
        methods, notes = import_methods(settings.source_dir, sources)
        selected = [p for p in pages if (p["source_id"], p["page"]) in {("S01", 10), ("S02", 6)}] if pilot else pages
        semaphore = asyncio.Semaphore(settings.ingest_concurrency)
        transport = IngestionTransport(settings)
        # Every task is awaited even after a failure, so completed cache entries remain resumable.
        async def job(page):
            try:
                return await process_page(page, staged, settings, fingerprint, semaphore, refresh, transport)
            except Exception as error:
                code = error.code if isinstance(error, ProviderError) else type(error).__name__
                if isinstance(error, ProviderError) and isinstance(getattr(error, "invalid_content", None), str):
                    write_json(staged / "diagnostics" / f"{page['source_id']}-p{page['page']:03}.json",
                               {"source_id": page["source_id"], "page": page["page"], "code": code,
                                "finish_reason": getattr(error, "finish_reason", None), "model_content": error.invalid_content})
                print(f"{page['source_id']} p.{page['page']}: failed ({code}); retained for retry", flush=True)
                return error
        results = await asyncio.gather(*[job(p) for p in selected])
        failures = [{"source_id": p["source_id"], "page": p["page"],
                     "code": r.code if isinstance(r, ProviderError) else type(r).__name__,
                     "upstream_status": r.upstream_status if isinstance(r, ProviderError) else None,
                     "upstream_code": r.upstream_code if isinstance(r, ProviderError) else None,
                     "message": str(r) if isinstance(r, (ProviderError, ValueError)) else "Page extraction failed"}
                    for p, r in zip(selected, results, strict=True) if isinstance(r, Exception)]
        successful = [r for r in results if not isinstance(r, Exception)]
        passages = sorted([record for records, _ in successful for record in records], key=lambda r: r["evidence_id"])
        coverage = [c for _, c in successful]
        checks_path = root / "source_checks.json"
        checks = read_json(checks_path) if checks_path.exists() else []
        apply_source_checks(passages, checks, pages)
        for item in coverage:
            item["eligible"] = sum(r["retrieval_eligible"] for r in passages
                                   if r["source_id"] == item["source_id"] and r["page"] == item["page"])
        write_json(staged / "failures.json", failures)
        write_json(staged / "method_notes.json", notes)
        write_json(staged / "methods.json", methods)
        (staged / "passages.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in passages), encoding="utf-8")
        manifest = {"schema_version": SCHEMA_VERSION, "sources": sources, "pipeline": fingerprint,
                    "project_source_checks": checks,
                    "coverage": sorted(coverage, key=lambda c: (c["source_id"], c["page"])),
                    "missing_optional_files": [name for name in MISSING_OPTIONAL if not (settings.source_dir / name).exists()],
                    "review_policy": "Automated validation; optional human verification; no AFS approval implied"}
        if failures:
            manifest.update(corpus_version="unpublished-incomplete-build", artifacts={})
            write_json(staged / "source_manifest.json", manifest)
            render_report(staged)
            raise ValueError(f"{len(failures)} page jobs failed; see {staged / 'failures.json'}. Rerun to resume valid caches.")
        if pilot:
            manifest.update(corpus_version="unpublished-pilot", artifacts={})
            write_json(staged / "source_manifest.json", manifest)
            render_report(staged)
            write_json(staged / "build_status.json", {"status": "pilot_passed", "pages": len(selected), "published": False})
            return staged / "review.html"
        print("Building local embeddings and Qdrant/BM25 indexes...", flush=True)
        embedder = Embedder(settings.embedding_cache_dir)
        version = "corpus-" + digest({"manifest": manifest, "passages": passages, "methods": methods,
                                       "notes": notes, "embedding": embedder.fingerprint})[:20]
        manifest["corpus_version"] = version
        build_indexes(staged, passages + methods, version, embedder)
        # Report embeds the inventory before checksums, avoiding a self-referential hash.
        manifest["artifacts"] = {}
        write_json(staged / "source_manifest.json", manifest)
        render_report(staged)
        artifact_names = ["passages.jsonl", "methods.json", "method_notes.json", "raw_pages.json",
                          "segments.json", "bm25.json", "index_manifest.json", "review.html"]
        manifest["artifacts"] = {name: file_hash(staged / name) for name in artifact_names}
        write_json(staged / "source_manifest.json", manifest)
        report = validate_corpus(staged, source_dir=settings.source_dir, deep=True)
        write_json(staged / "validation_report.json", report)
        manifest["artifacts"]["validation_report.json"] = file_hash(staged / "validation_report.json")
        write_json(staged / "source_manifest.json", manifest)
        write_json(staged / "build_status.json", {"status": "passed", "finished_at": utc_now()})
        final = publish(root, staged, manifest)
        print(json.dumps(report, indent=2), flush=True)
        return final / "review.html"
    except BaseException as error:
        write_json(staged / "build_status.json", {"status": "failed", "finished_at": utc_now(),
                   "code": error.code if isinstance(error, ProviderError) else type(error).__name__})
        raise


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["build", "pilot"]:
        command = commands.add_parser(name)
        command.add_argument("--refresh", action="store_true", help="Explicitly rerun page extraction and verification")
        command.add_argument("--provider", choices=["groq", "llmtech"])
        command.add_argument("--public-trial", action="store_true", help="Fetch LLMTech's documented public trial key at runtime")
    commands.add_parser("validate")
    commands.add_parser("report")
    command = commands.add_parser("search")
    command.add_argument("--query", required=True)
    args = parser.parse_args()
    settings = Settings()
    try:
        if args.command in {"build", "pilot"}:
            if args.provider == "llmtech":
                settings = settings.model_copy(update={"provider_name": "llmtech", "provider_base_url": "https://api.llmtech.eu/v1",
                    "provider_model": "nvidia/Qwen3.8-27B-NVFP4", "ingest_max_output_tokens": 8192,
                    "ingest_concurrency": 2, "provider_call_timeout_s": 120, "request_deadline_s": 300})
            elif args.provider:
                settings = settings.model_copy(update={"provider_name": args.provider})
            if args.public_trial:
                if settings.provider_name != "llmtech":
                    raise ValueError("--public-trial requires --provider llmtech")
                if not settings.provider_configured:
                    import re
                    import httpx
                    from pydantic import SecretStr
                    response = httpx.get("https://llmtech.eu/docs/", timeout=30, follow_redirects=False)
                    response.raise_for_status()
                    match = re.search(r"lt-trial-[0-9a-f]+", response.text)
                    if not match:
                        raise ValueError("No public trial key found in official LLMTech documentation")
                    settings = settings.model_copy(update={"llmtech_api_key": SecretStr(match.group())})
            print(asyncio.run(build(settings, refresh=args.refresh, pilot=args.command == "pilot")))
        elif args.command == "validate":
            print(json.dumps(validate_corpus(active_directory(settings.corpus_dir), source_dir=settings.source_dir, deep=True), indent=2))
        elif args.command == "report":
            # A published generation is immutable: its report already matches manifest checksums.
            directory = active_directory(settings.corpus_dir)
            validate_corpus(directory)
            print(directory / "review.html")
        else:
            from backend.retrieval import search
            print(json.dumps(search(settings.corpus_dir, settings.embedding_cache_dir, args.query), indent=2, ensure_ascii=False))
        return 0
    except (ProviderError, ValueError, OSError, KeyError, ImportError) as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
