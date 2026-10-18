"""Local readiness checks. No provider calls or implied human approval."""
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ValidationError
from backend.knowledge_store import active_directory, validate_corpus

class CorpusStatus(BaseModel):
    status: Literal["missing", "unreadable", "invalid", "empty", "ready"]
    version: str | None = None
    eligible_passages: int = 0
    eligible_methods: int = 0
    flagged_records: int = 0
    human_verified_records: int = 0

class ProviderStatus(BaseModel):
    name: Literal["auto", "gemini", "groq", "llmtech"] = "auto"
    model: str
    configured: bool
    mode: Literal["auto", "gemini", "groq", "llmtech"] = "auto"
    selected: str | None = None
    candidates: list[dict] = Field(default_factory=list)

class HealthResponse(BaseModel):
    service: Literal["running"] = "running"
    ready: bool
    corpus: CorpusStatus
    provider: ProviderStatus

def inspect_corpus(directory: Path) -> CorpusStatus:
    try:
        report = validate_corpus(active_directory(directory))
        return CorpusStatus(status="ready", version=report["corpus_version"],
                            eligible_passages=report["eligible_passages"], eligible_methods=report["eligible_methods"],
                            flagged_records=report["flagged"], human_verified_records=report["human_verified"])
    except FileNotFoundError:
        return CorpusStatus(status="invalid" if (directory / "current.json").exists() else "missing")
    except OSError:
        return CorpusStatus(status="unreadable")
    except (ValueError, TypeError, KeyError, IndexError, StopIteration, ValidationError, UnicodeError):
        return CorpusStatus(status="invalid")
