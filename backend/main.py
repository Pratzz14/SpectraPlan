"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

from fastapi import FastAPI

from backend.config import Settings
from backend.health import HealthResponse, ProviderStatus, inspect_corpus


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    application = FastAPI(title="SpectraPlan", version="0.1.0")

    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        corpus = inspect_corpus(config.corpus_dir)
        return HealthResponse(
            ready=config.provider_configured and corpus.status == "ready",
            corpus=corpus,
            provider=ProviderStatus(model=config.provider_model, configured=config.provider_configured),
        )

    return application


app = create_app()
