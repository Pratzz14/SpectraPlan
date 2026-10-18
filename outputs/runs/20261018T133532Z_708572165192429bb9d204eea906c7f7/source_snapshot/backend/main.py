"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

import json
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.config import Settings
from backend.agent import extract_case, assess_case
from backend.models import CaseFacts, ExtractionRequest, AssessmentRequest, AssessmentRun
from backend.provider import Provider, ProviderError
from backend.health import HealthResponse, ProviderStatus, inspect_corpus
from backend.knowledge_store import active_directory, inside, read_json, inventory
from backend.knowledge_report import inspection_data
from backend.search_service import SearchService, SearchUnavailable
from backend.evidence import CorpusUnavailable, EvidenceNotFound, EvidenceRevisionMismatch, ResolvedEvidence, load_snapshot
from backend.retrieval import CaseRetrievalService, RetrievalTimeout, SEARCH_LOCK
from backend.retrieval_models import RetrievalResult
from backend.explainability import ExplainabilityStore, HistoryConflict, compose_description, question_id


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
        explainability_store.recover_interrupted()
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
    explainability_store = ExplainabilityStore(config.explainability_db_path)
    application.state.retrieval_service = retrieval_service

    @application.post("/api/assess", response_model=AssessmentRun,
                      responses={422: {"description": "Invalid enquiry"},
                                 502: {"model": AssessmentRun}, 503: {"model": AssessmentRun},
                                 504: {"model": AssessmentRun}})
    async def assess(request: AssessmentRequest):
        answers = [answer.model_dump(mode="json") for answer in request.clarification_answers]
        effective = compose_description(request.description, answers)
        if len(effective) > config.assessment_max_description_chars:
            raise HTTPException(422, {"code":"description_too_long",
                "message":f"Enquiry including clarifications exceeds {config.assessment_max_description_chars} characters."})
        identity = None
        try:
            identity = explainability_store.begin(request.description, answers,
                enquiry_id=request.enquiry_id, parent_run_id=request.parent_run_id)
            run_id = identity["run_id"]
            def record_event(event):
                explainability_store.append(run_id, event)
            def record_stage(stage, value):
                record_event({"stage":stage,"event_type":"validated_stage","payload":value.model_dump(mode="json")})
            result = await assess_case(identity["effective_description"], config, retrieval_service=retrieval_service,
                on_stage=record_stage, on_event=record_event, run_id=run_id)
            result.metadata.enquiry_id = identity["enquiry_id"]
            result.metadata.parent_run_id = identity["parent_run_id"]
            result.metadata.round_no = identity["round_no"]
            result.metadata.question_ids = [question_id(run_id, q.model_dump())
                for q in result.assessment.clarification_questions] if result.assessment else []
            explainability_store.finish(run_id, result.model_dump(mode="json"))
        except HistoryConflict as error:
            raise HTTPException(409, {"code":"history_conflict","message":str(error)}) from None
        except (OSError, sqlite3.Error):
            raise HTTPException(503, {"code":"explainability_unavailable",
                "message":"Assessment history could not be stored. Retry when local storage is available."}) from None
        except BaseException:
            if identity:
                explainability_store.interrupt(identity["run_id"])
            raise
        status = result.errors[0].http_status if result.facts is None and result.errors else 200
        response_payload = result.model_dump(mode="json")
        response_payload["metadata"]["provider_trace"] = []
        return JSONResponse(response_payload, status_code=status)

    def history_read(method, *args):
        try:
            value = method(*args)
        except (OSError, sqlite3.Error):
            raise HTTPException(503, {"code":"explainability_unavailable","message":"Enquiry history is unavailable."}) from None
        if value is None:
            raise HTTPException(404, {"code":"history_not_found","message":"Saved history was not found."})
        return value

    @application.get("/api/assess/{run_id}/explainability")
    def explainability(run_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise HTTPException(422, {"code":"invalid_run_id","message":"Invalid assessment run ID."})
        return history_read(explainability_store.read, run_id)

    @application.get("/api/enquiries")
    def enquiries(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        return history_read(explainability_store.list_enquiries, limit, offset)

    @application.get("/api/assess/{run_id}/report.pdf")
    def saved_report(run_id: str, audience: Literal['chemist', 'trace'] = 'chemist'):
        from backend.history_pdf import history_pdf, chemist_pdf
        trace = explainability(run_id)
        return Response((history_pdf if audience == 'trace' else chemist_pdf)(trace), media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="spectraplan-{run_id}.pdf"',
            "Cache-Control": "no-store"})

    @application.get("/api/enquiries/{enquiry_id}")
    def enquiry(enquiry_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", enquiry_id):
            raise HTTPException(422, {"code":"invalid_enquiry_id","message":"Invalid enquiry ID."})
        return history_read(explainability_store.enquiry, enquiry_id)

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

    @application.get("/api/knowledge/gemini-comparison")
    def gemini_comparison():
        path = config.smoke_output_dir / "gemini_complete_comparison.json"
        try:
            data = read_json(path)
            if not isinstance(data, dict) or data.get("model") != config.gemini_model or not isinstance(data.get("results"), list):
                raise ValueError("Invalid Gemini comparison artifact")
            if not all(isinstance(result, dict) for result in data["results"]):
                raise ValueError("Invalid comparison source result")
            sources = {source["source_id"]: source["sha256"] for source in inventory(config.source_dir)}
            if (not isinstance(data.get("succeeded"), int) or
                any(result.get("source_sha256") != sources.get(result.get("source_id")) or
                    result.get("source_sha256") is None for result in data["results"])):
                raise ValueError("Comparison is outdated; regenerate from current sources")
            return data
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            raise HTTPException(404, "Gemini comparison is unavailable. Run the comparison command first.") from None

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
