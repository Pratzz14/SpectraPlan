"""ASGI entrypoint: python -m uvicorn backend.main:app."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.core.config import Settings
from backend.services.search.search_service import SearchService
from backend.services.search.retrieval import CaseRetrievalService
from backend.services.history.explainability import ExplainabilityStore


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application):
        explainability_store.recover_interrupted()
        yield

    application = FastAPI(title="SpectraPlan", version="0.1.0", lifespan=lifespan)
    search_service = SearchService(config)
    retrieval_service = CaseRetrievalService(config)
    explainability_store = ExplainabilityStore(config.explainability_db_path)
    application.state.settings = config
    application.state.search_service = search_service
    application.state.explainability_store = explainability_store
    application.state.retrieval_service = retrieval_service

    from backend.api.routes import create_router
    application.include_router(create_router())

    return application


app = create_app()
