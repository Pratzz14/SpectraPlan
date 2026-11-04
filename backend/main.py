"""ASGI entrypoint: python -m uvicorn backend.main:app."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.core.config import Settings
from backend.services.search.search_service import SearchService
from backend.services.search.retrieval import CaseRetrievalService
from backend.services.history.explainability import ExplainabilityStore


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    database = None
    knowledge = None
    if config.storage_backend == 'supabase':
        from backend.services.cloud.database import Database
        from backend.services.cloud.storage import ArtifactStorage
        from backend.services.cloud.knowledge import CloudKnowledge
        from backend.services.cloud.history import PostgresHistory
        database = Database(config)
        knowledge = CloudKnowledge(config, database, ArtifactStorage(config))
        explainability_store = PostgresHistory(database)
    else:
        explainability_store = ExplainabilityStore(config.explainability_db_path)

    @asynccontextmanager
    async def lifespan(application):
        import asyncio
        from backend.services.cloud.database import StorageUnavailable
        try:
            await asyncio.to_thread(explainability_store.recover_interrupted)
        except StorageUnavailable:
            pass
        async def recover_stale_runs():
            while True:
                await asyncio.sleep(60)
                try:
                    await asyncio.to_thread(explainability_store.recover_interrupted)
                except StorageUnavailable:
                    pass
        recovery = asyncio.create_task(recover_stale_runs()) if database else None
        try:
            yield
        finally:
            if recovery:
                recovery.cancel()
                from contextlib import suppress
                with suppress(asyncio.CancelledError):
                    await recovery
            if database:
                database.close()

    application = FastAPI(title="SpectraPlan", version="0.1.0", lifespan=lifespan)
    @application.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
    search_service = SearchService(config, repository=knowledge)
    retrieval_service = CaseRetrievalService(config, repository=knowledge)
    application.state.settings = config
    application.state.search_service = search_service
    application.state.explainability_store = explainability_store
    application.state.retrieval_service = retrieval_service
    application.state.knowledge_repository = knowledge

    from backend.services.cloud.database import StorageUnavailable
    from fastapi.responses import JSONResponse
    @application.exception_handler(StorageUnavailable)
    async def storage_failure(request, error):
        return JSONResponse({'detail': 'Supabase storage is unavailable. Check connectivity and configuration.'}, status_code=503,
                            headers={'Cache-Control': 'no-store'})

    from backend.api.routes import create_router
    application.include_router(create_router())

    return application


app = create_app()
