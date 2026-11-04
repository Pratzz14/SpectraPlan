"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

from backend.api.auth import require_admin

from backend.api.dependencies import get_settings, get_knowledge


from fastapi import Depends, APIRouter

from backend.core.config import Settings
from backend.services.health import HealthResponse, ProviderStatus, inspect_corpus


def create_router():
    router = APIRouter(tags=["Health"], dependencies=[Depends(require_admin)])
    @router.get("/api/health", response_model=HealthResponse)
    def health(config: Settings = Depends(get_settings), knowledge=Depends(get_knowledge)) -> HealthResponse:
        if knowledge:
            from backend.services.health import CorpusStatus
            from backend.services.cloud.database import StorageUnavailable
            from backend.services.search.evidence import CorpusUnavailable, EvidenceNotFound
            try:
                snapshot = knowledge.snapshot()
                rows = list(snapshot.records.values())
                corpus = CorpusStatus(status='ready' if rows else 'empty', version=snapshot.version,
                    eligible_passages=sum(r['content_kind']!='method_row' for r in rows),
                    eligible_methods=sum(r['content_kind']=='method_row' for r in rows),
                    human_verified_records=sum(r.get('human_review_status')=='verified' for r in rows))
            except (StorageUnavailable, CorpusUnavailable, EvidenceNotFound):
                corpus = CorpusStatus(status='unreadable')
        else:
            corpus = inspect_corpus(config.corpus_dir)
        return HealthResponse(ready=config.provider_configured and corpus.status == "ready", corpus=corpus,
            provider=ProviderStatus(name="dashscope", mode="dashscope", model=config.provider_model,
                configured=config.provider_configured, selected="dashscope" if config.provider_configured else None,
                candidates=[{"name":"dashscope", "configured":config.provider_configured,
                    "status":"unchecked" if config.provider_configured else "not_configured", "error_code":None}]))
    return router
