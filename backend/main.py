"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

import re
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.config import Settings
from backend.agent import extract_case, assess_case
from backend.models import CaseFacts, ExtractionRequest, AssessmentRequest, AssessmentRun
from backend.provider import Provider, ProviderError
from backend.health import HealthResponse, ProviderStatus, inspect_corpus
from backend.knowledge_store import active_directory, inside, read_json
from backend.knowledge_report import inspection_data
from backend.search_service import SearchService, SearchUnavailable
from backend.evidence import CorpusUnavailable, EvidenceNotFound, EvidenceRevisionMismatch, ResolvedEvidence, load_snapshot
from backend.retrieval import CaseRetrievalService, RetrievalTimeout, SEARCH_LOCK
from backend.retrieval_models import RetrievalResult


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["compare", "bm25", "qdrant", "hybrid"] = "compare"
    dataset: Literal["technical", "website", "all"] = "technical"
    limit: int = Field(default=6, ge=1, le=8)
    expand_synonyms: bool = True

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a search query")
        return value.strip()


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application):
        if config.provider_name == "auto" and config.provider_configured:
            try:
                await Provider(config).check(deadline=time.monotonic() + min(
                    config.request_deadline_s, config.provider_probe_timeout_s * len(config.provider_names)))
            except ProviderError:
                pass  # Readiness exposes availability; later requests retry after cooldown.
        yield

    application = FastAPI(title="SpectraPlan", version="0.1.0", lifespan=lifespan)
    search_service = SearchService(config)
    retrieval_service = CaseRetrievalService(config)
    application.state.retrieval_service = retrieval_service

    @application.post("/api/assess", response_model=AssessmentRun,
                      responses={422: {"description": "Invalid enquiry"},
                                 502: {"model": AssessmentRun}, 503: {"model": AssessmentRun},
                                 504: {"model": AssessmentRun}})
    async def assess(request: AssessmentRequest):
        if len(request.description) > config.assessment_max_description_chars:
            raise HTTPException(422, {"code": "description_too_long",
                "message": f"Description limit is {config.assessment_max_description_chars} characters."})
        result = await assess_case(request.description, config, retrieval_service=retrieval_service)
        status = result.errors[0].http_status if result.facts is None and result.errors else 200
        return JSONResponse(result.model_dump(mode="json"), status_code=status)

    @application.post("/api/retrieve", response_model=RetrievalResult)
    def retrieve(facts: CaseFacts):
        try:
            return retrieval_service.retrieve_case(facts)
        except RetrievalTimeout as error:
            raise HTTPException(504, {"code": "retrieval_timeout", "message": str(error)}) from None
        except CorpusUnavailable as error:
            raise HTTPException(503, {"code": "retrieval_unavailable", "message": str(error)}) from None
        except ValueError as error:
            raise HTTPException(422, {"code": "invalid_contexts", "message": str(error)}) from None

    @application.get("/api/evidence/{evidence_id}", response_model=ResolvedEvidence)
    def evidence(evidence_id: str, corpus_version: str | None = None, revision: str | None = None):
        if not SEARCH_LOCK.acquire(timeout=30):
            raise HTTPException(503, {"code": "evidence_unavailable", "message": "Evidence search is busy"})
        try:
            return load_snapshot(config.corpus_dir, corpus_version).resolve(evidence_id, revision)
        except EvidenceNotFound as error:
            raise HTTPException(404, {"code": "evidence_not_found", "message": str(error)}) from None
        except EvidenceRevisionMismatch as error:
            raise HTTPException(409, {"code": "evidence_revision_mismatch", "message": str(error)}) from None
        except CorpusUnavailable as error:
            raise HTTPException(503, {"code": "evidence_unavailable", "message": str(error)}) from None
        finally:
            SEARCH_LOCK.release()

    @application.post("/api/extract", response_model=CaseFacts)
    async def extract(request: ExtractionRequest):
        try:
            return await extract_case(request.description, config)
        except ProviderError as error:
            raise HTTPException(error.http_status, {"code": error.code, "message": str(error)}) from None

    @application.get("/api/search/status")
    def search_status():
        return search_service.status()

    @application.post("/api/search")
    def query_search(request: SearchRequest):
        try:
            return search_service.compare(**request.model_dump())
        except SearchUnavailable as error:
            raise HTTPException(503, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        corpus = inspect_corpus(config.corpus_dir)
        router = config._provider_router
        route = router.snapshot() if router is not None else {"selected": None, "candidates": [
            {"name": name, "configured": config.usable_key(getattr(config, f"{name}_api_key")),
             "status": "unchecked" if config.usable_key(getattr(config, f"{name}_api_key")) else "not_configured",
             "error_code": None} for name in config.provider_names]}
        selected = route["selected"]
        identity = config.for_provider(selected) if selected else config
        return HealthResponse(
            ready=config.provider_configured and corpus.status == "ready" and (config.provider_name != "auto" or selected is not None),
            corpus=corpus,
            provider=ProviderStatus(name=selected or config.provider_name, model=identity.provider_model,
                configured=config.provider_configured, mode=config.provider_name,
                selected=selected, candidates=route["candidates"]),
        )

    @application.get("/api/knowledge/inspection")
    def knowledge_inspection():
        try:
            directory = active_directory(config.corpus_dir)
            data = inspection_data(directory)
            version = data["manifest"]["corpus_version"]
            if not re.fullmatch(r"corpus-[a-f0-9]{20}", version) or directory.name != version:
                raise ValueError("No published corpus")
            return {**data, "artifact_base": f"/api/knowledge/versions/{version}/"}
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(503, "Published extracted knowledge is unavailable. Check workspace status.") from None

    @application.get("/api/knowledge/report", include_in_schema=False)
    def knowledge_report():
        try:
            directory = active_directory(config.corpus_dir)
            version = read_json(directory / "source_manifest.json")["corpus_version"]
            if not re.fullmatch(r"corpus-[a-f0-9]{20}", version):
                raise ValueError("Invalid corpus version")
            return RedirectResponse(f"/api/knowledge/versions/{version}/review.html", status_code=307)
        except (OSError, ValueError, KeyError):
            raise HTTPException(404, "No published knowledge report. Build the corpus first.") from None

    @application.get("/api/knowledge/versions/{version}/{artifact:path}", include_in_schema=False)
    def knowledge_artifact(version: str, artifact: str):
        if not re.fullmatch(r"corpus-[a-f0-9]{20}", version):
            raise HTTPException(404, "Unknown corpus")
        try:
            directory = config.corpus_dir / "versions" / version
            allowed = {"review.html"} | {p["image"] for p in read_json(directory / "raw_pages.json")}
            if artifact not in allowed:
                raise ValueError("Unknown artifact")
            path = inside(directory, artifact)
            if not path.is_file():
                raise ValueError("Missing artifact")
            return FileResponse(path)
        except (OSError, ValueError, KeyError):
            raise HTTPException(404, "Unknown corpus artifact") from None

    return application


app = create_app()
