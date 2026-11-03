"""Inspectable retrieval candidates and gaps, not scientific assessment decisions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.services.search.evidence import ResolvedEvidence

Facet = Literal["application", "geometry", "compatibility", "limitations"]


class RetrievalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class EvidenceMatch(RetrievalModel):
    query_id: str
    context_id: str
    facets: list[Facet]
    admission: Literal["lexical", "semantic_only", "structured"]
    bm25_score: float | None = None
    bm25_rank: int | None = None
    cosine_score: float | None = None
    dense_rank: int | None = None
    rrf_score: float
    matched_terms: list[str]
    matching_segment: str | None = None


class CandidateDecision(RetrievalModel):
    evidence_id: str
    admitted: bool
    reason: str
    match: EvidenceMatch
    source_id: str | None = None
    file_name: str | None = None


class QueryTrace(RetrievalModel):
    query_id: str
    context_id: str
    facet: Literal["context", "application", "geometry", "compatibility", "limitations", "method_table"]
    round: int
    query: str
    source_fields: dict[str, list[str]]
    omitted_terms: list[str] = Field(default_factory=list)
    expanded_terms: list[str] = Field(default_factory=list)
    statements: list[dict] = Field(default_factory=list)
    candidates: list[CandidateDecision] = Field(default_factory=list)
    bm25_tokens: list[str] = Field(default_factory=list)
    embedding_input: str | None = None
    branch_rankings: dict[str, list[dict]] = Field(default_factory=dict)


class LedgerEntry(RetrievalModel):
    evidence: ResolvedEvidence
    context_ids: list[str]
    facets: list[Facet]
    matches: list[EvidenceMatch]
    score: float
    selection_reasons: list[str]


class EvidenceGap(RetrievalModel):
    context_id: str | None = None
    facet: Facet | None = None
    reason: Literal["no_relevant_evidence", "budget_limit", "missing_context", "unspecified_input"]
    message: str


class EvidenceCoverage(RetrievalModel):
    context_id: str
    facet: Facet
    status: Literal["candidate_found", "gap"]
    evidence_ids: list[str]


class RetrievalResult(RetrievalModel):
    status: Literal["ok"] = "ok"
    corpus_version: str
    retrieval_version: str
    ranking: str = "BM25 + local BGE cosine, RRF k=60; structured method lookup"
    semantic_min_score: float
    max_records: int = 8
    search_rounds: int = Field(ge=0, le=2)
    evidence: list[LedgerEntry] = Field(max_length=8)
    queries: list[QueryTrace]
    coverage: list[EvidenceCoverage]
    gaps: list[EvidenceGap]
    warnings: list[str]
    model_calls: int = 0
