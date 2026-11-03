"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

from backend.api.dependencies import get_settings


from fastapi import Depends, APIRouter

from backend.core.config import Settings
from backend.services.health import HealthResponse, ProviderStatus, inspect_corpus


def create_router():
    router = APIRouter(tags=["Health"])
    @router.get("/api/health", response_model=HealthResponse)
    def health(config: Settings = Depends(get_settings)) -> HealthResponse:
        corpus = inspect_corpus(config.corpus_dir)
        return HealthResponse(ready=config.provider_configured and corpus.status == "ready", corpus=corpus,
            provider=ProviderStatus(name="dashscope", mode="dashscope", model=config.provider_model,
                configured=config.provider_configured, selected="dashscope" if config.provider_configured else None,
                candidates=[{"name":"dashscope", "configured":config.provider_configured,
                    "status":"unchecked" if config.provider_configured else "not_configured", "error_code":None}]))
    return router
