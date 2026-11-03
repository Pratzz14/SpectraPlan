"""Opt-in Gemini extraction comparison for original source files."""

import json
import time
from typing import Any, Callable
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from backend.config import Settings
from backend.knowledge_store import extract_original_documents, inventory


class GeminiExtractionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class GeminiExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    claims: list[str] = Field(default_factory=list, max_length=8)
    facts: list[str] = Field(default_factory=list, max_length=8)
    unknowns: list[str] = Field(default_factory=list, max_length=8)
    source_locations: list[str] = Field(default_factory=list, max_length=20)


def _prompt(document: dict) -> str:
    payload = {
        "source_id": document["source_id"],
        "file_name": document["file_name"],
        "format": document["format"],
        "blocks": [{"location": b["location"], "text": b["text"]} for b in document["blocks"]],
    }
    return (
        "Extract only information explicitly present in this source document. "
        "Return one JSON object with source_id as a string and exactly these arrays: claims, facts, "
        "unknowns, source_locations. Return at most 8 claims, 8 facts, 8 unknowns, "
        "and 20 source_locations. Keep claims and facts concise and quote or "
        "paraphrase only the supplied blocks. Do not invent technical conclusions. "
        "source_locations must use the supplied location values.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


async def extract_with_gemini(document: dict, settings: Settings, *, client: Any = None,
                              timeout_s: float | None = None) -> GeminiExtraction:
    from backend.provider import Provider, ProviderError
    if not settings.gemini_configured:
        raise GeminiExtractionError("gemini_not_configured", "Set GEMINI_API_KEY on the backend.")
    config = settings.for_provider("gemini")
    adapter = Provider(config, gemini_client=client)
    adapter.stage = "document_comparison"
    deadline = time.monotonic() + (timeout_s or settings.provider_call_timeout_s)
    try:
        result = await adapter.structured([{"role":"user","content":_prompt(document)}],
            GeminiExtraction, deadline=deadline, max_completion_tokens=settings.gemini_max_output_tokens)
        allowed = {block["location"] for block in document["blocks"]}
        if result.source_id != document["source_id"] or not set(result.source_locations) <= allowed:
            raise GeminiExtractionError("gemini_invalid_provenance", "Gemini returned an unknown source ID or location.")
        return result
    except ProviderError as error:
        raise GeminiExtractionError(error.code, str(error)) from None


async def compare_original_extraction(settings: Settings, *, client: Any = None,
                                      baseline: Callable[[dict], dict] | None = None,
                                      source_limit: int | None = None,
                                      source_ids: set[str] | None = None) -> dict:
    started = time.monotonic()
    sources = inventory(settings.source_dir)
    documents = extract_original_documents(settings.source_dir, sources)
    if source_ids:
        if source_ids - {document["source_id"] for document in documents}:
            raise ValueError("Unknown or unsupported source ID")
        documents = [document for document in documents if document["source_id"] in source_ids]
    if source_limit is not None:
        if source_limit < 1:
            raise ValueError("source_limit must be positive")
        documents = documents[:source_limit]
    baseline = baseline or (lambda document: {
        "source_id": document["source_id"],
        "claims": [],
        "facts": [block["text"] for block in document["blocks"]],
        "unknowns": [],
        "source_locations": [block["location"] for block in document["blocks"]],
    })
    results = []
    for document in documents:
        baseline_result = baseline(document)
        try:
            gemini_result = (await extract_with_gemini(document, settings, client=client)).model_dump()
            error = None
        except GeminiExtractionError as failure:
            gemini_result = None
            error = {"code": failure.code, "message": str(failure)}
        results.append({"source_id": document["source_id"], "file_name": document["file_name"],
                        "source_sha256": document.get("source_sha256"), "baseline": baseline_result, "gemini": gemini_result, "error": error})
    return {"model": settings.gemini_model, "source_count": len(documents),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "succeeded": sum(r["gemini"] is not None for r in results),
            "errors": sum(r["error"] is not None for r in results),
            "results": results, "elapsed_s": round(time.monotonic() - started, 3)}
