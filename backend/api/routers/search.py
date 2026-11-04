"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

from backend.api.auth import require_admin

from backend.api.dependencies import get_settings, get_search, get_retrieval, get_knowledge


from fastapi import Depends, APIRouter, HTTPException

from backend.core.config import Settings
from backend.schemas.models import CaseFacts
from backend.services.search.search_service import SearchService, SearchUnavailable
from backend.services.search.evidence import CorpusUnavailable, EvidenceNotFound, EvidenceRevisionMismatch, ResolvedEvidence, load_snapshot
from backend.services.search.retrieval import CaseRetrievalService, RetrievalTimeout, SEARCH_LOCK
from backend.schemas.retrieval_models import RetrievalResult



from backend.schemas.search import SearchRequest

def create_router():
    router = APIRouter(tags=["Search"], dependencies=[Depends(require_admin)])
    @router.post("/api/retrieve", response_model=RetrievalResult)
    def retrieve(facts: CaseFacts, retrieval_service: CaseRetrievalService = Depends(get_retrieval)):
        try:
            return retrieval_service.retrieve_case(facts)
        except RetrievalTimeout as error:
            raise HTTPException(504, {"code": "retrieval_timeout", "message": str(error)}) from None
        except CorpusUnavailable as error:
            raise HTTPException(503, {"code": "retrieval_unavailable", "message": str(error)}) from None
        except ValueError as error:
            raise HTTPException(422, {"code": "invalid_contexts", "message": str(error)}) from None


    @router.get("/api/evidence/{evidence_id}", response_model=ResolvedEvidence)
    def evidence(evidence_id: str, corpus_version: str | None = None, revision: str | None = None, config: Settings = Depends(get_settings), knowledge=Depends(get_knowledge)):
        if not SEARCH_LOCK.acquire(timeout=30):
            raise HTTPException(503, {"code": "evidence_unavailable", "message": "Evidence search is busy"})
        try:
            snapshot = knowledge.snapshot(corpus_version) if knowledge else load_snapshot(config.corpus_dir, corpus_version)
            return snapshot.resolve(evidence_id, revision)
        except EvidenceNotFound as error:
            raise HTTPException(404, {"code": "evidence_not_found", "message": str(error)}) from None
        except EvidenceRevisionMismatch as error:
            raise HTTPException(409, {"code": "evidence_revision_mismatch", "message": str(error)}) from None
        except CorpusUnavailable as error:
            raise HTTPException(503, {"code": "evidence_unavailable", "message": str(error)}) from None
        finally:
            SEARCH_LOCK.release()


    @router.get("/api/search/status")
    def search_status(search_service: SearchService = Depends(get_search)):
        return search_service.status()


    @router.post("/api/search")
    def query_search(request: SearchRequest, search_service: SearchService = Depends(get_search)):
        try:
            return search_service.compare(**request.model_dump())
        except SearchUnavailable as error:
            raise HTTPException(503, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    return router
