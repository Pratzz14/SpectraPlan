"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from backend.config import Settings
from backend.health import HealthResponse, ProviderStatus, inspect_corpus
from backend.knowledge_store import active_directory, inside, read_json


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    application = FastAPI(title="SpectraPlan", version="0.1.0")

    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        corpus = inspect_corpus(config.corpus_dir)
        return HealthResponse(
            ready=config.provider_configured and corpus.status == "ready",
            corpus=corpus,
            provider=ProviderStatus(name=config.provider_name, model=config.provider_model, configured=config.provider_configured),
        )

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
