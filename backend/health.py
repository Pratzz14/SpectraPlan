"""Cheap local corpus checks, independent of any model call or ingestion."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CorpusStatus(BaseModel):
    status: Literal["missing", "unreadable", "invalid", "empty", "ready"]
    version: str | None = None
    approved_passages: int = 0
    approved_methods: int = 0


class ProviderStatus(BaseModel):
    name: Literal["groq"] = "groq"
    model: str
    configured: bool


class HealthResponse(BaseModel):
    service: Literal["running"] = "running"
    ready: bool
    corpus: CorpusStatus
    provider: ProviderStatus


class _Evidence(BaseModel):
    # These minimum location/review fields are shared by passages and method rows.
    # F02 supplies the full ingestion contract and scientific source review.
    model_config = ConfigDict(extra="allow", strict=True)
    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    revision: str = Field(min_length=1)
    approval_status: Literal["approved", "unreviewed", "rejected"]


class _Passage(_Evidence):
    file_name: str = Field(min_length=1)
    text: str = Field(min_length=1)


class _Method(_Evidence):
    method: str = Field(min_length=1)
    geometry: str = Field(min_length=1)


def inspect_corpus(directory: Path) -> CorpusStatus:
    """Never infer readiness from directory existence or hide a broken corpus."""
    try:
        manifest = json.loads((directory / "source_manifest.json").read_text(encoding="utf-8"))
        passages = [
            _Passage.model_validate(json.loads(line))
            for line in (directory / "passages.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        methods = [
            _Method.model_validate(row)
            for row in json.loads((directory / "methods.json").read_text(encoding="utf-8"))
        ]
        version = manifest["corpus_version"]
        if not isinstance(version, str) or not version.strip():
            raise ValueError("Missing corpus version")
        sources = {source["source_id"] for source in manifest["sources"]}
        records = [*passages, *methods]
        if len({record.evidence_id for record in records}) != len(records):
            raise ValueError("Duplicate evidence IDs")
        if any(record.source_id not in sources or record.revision != version for record in records):
            raise ValueError("Unknown source or mismatched revision")
        approved_passages = sum(record.approval_status == "approved" for record in passages)
        approved_methods = sum(record.approval_status == "approved" for record in methods)
        return CorpusStatus(
            status="ready" if approved_passages and approved_methods else "empty",
            version=version,
            approved_passages=approved_passages,
            approved_methods=approved_methods,
        )
    except FileNotFoundError:
        return CorpusStatus(status="missing")
    except OSError:
        return CorpusStatus(status="unreadable")
    except (ValueError, TypeError, KeyError, ValidationError, UnicodeError):
        return CorpusStatus(status="invalid")
