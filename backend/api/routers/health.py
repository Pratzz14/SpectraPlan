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

    return router
