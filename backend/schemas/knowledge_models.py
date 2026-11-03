"""Versioned ingestion contracts. Model output never decides publication status."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "f02-v1"
EXTRACTOR_VERSION = "pymupdf-blocks-v1"
Scope = Literal["general_method", "application_example", "research_demonstration", "business_context", "development_example"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Span(StrictModel):
    block_id: str
    quote: str | None


class Region(StrictModel):
    # Relative coordinates on the rendered page, not PDF points.
    x0: float = Field(ge=0, le=1)
    y0: float = Field(ge=0, le=1)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    label: str


class Quantity(StrictModel):
    label: str
    value: str
    unit: str | None
    kind: Literal["spectral_range", "optical_path_or_depth", "fiber_link_length", "excitation_wavelength",
                  "raman_shift", "sample_count", "experimental_condition", "other"]
    source_quote: str


class Fact(StrictModel):
    category: Literal["method", "geometry", "sample", "phenomenon", "application", "equipment",
                      "experimental_scope", "limitation", "calibration", "other"]
    statement: str = Field(max_length=300)
    support_quotes: list[str] = Field(max_length=2)
    quantities: list[Quantity] = Field(max_length=3)


class Candidate(StrictModel):
    section: str
    content_kind: Literal["verbatim_text", "figure_transcription"]
    evidence_scope: Scope
    spans: list[Span]
    region: Region | None
    transcription: str | None = Field(max_length=1200)
    interpretation: str | None = Field(max_length=300)
    facts: list[Fact] = Field(max_length=1)
    tags: list[str] = Field(max_length=4)
    issues: list[str] = Field(max_length=3)


class TextGroup(StrictModel):
    section: str
    evidence_scope: Scope
    block_ids: list[str] = Field(min_length=1, max_length=40)
    facts: list[Fact] = Field(max_length=1)
    tags: list[str] = Field(max_length=4)


class FigureGroup(StrictModel):
    section: str
    evidence_scope: Scope
    region: Region
    transcription: str = Field(min_length=1, max_length=1200)
    interpretation: str | None = Field(max_length=300)
    facts: list[Fact] = Field(max_length=1)
    tags: list[str] = Field(max_length=4)
    issues: list[str] = Field(max_length=3)


class PageExtraction(StrictModel):
    text_groups: list[TextGroup] = Field(max_length=4)
    figures: list[FigureGroup] = Field(max_length=4)
    empty_reason: str | None
    issues: list[str]

    @property
    def candidates(self) -> list[Candidate]:
        return [Candidate(section=g.section, content_kind="verbatim_text", evidence_scope=g.evidence_scope,
                          spans=[Span(block_id=bid, quote=None) for bid in g.block_ids], region=None,
                          transcription=None, interpretation=None, facts=g.facts, tags=g.tags, issues=[])
                for g in self.text_groups] + [Candidate(content_kind="figure_transcription", spans=[], **g.model_dump())
                                             for g in self.figures]


class Verdict(StrictModel):
    candidate_index: int = Field(ge=0, le=7)
    status: Literal["supported", "unsupported", "ambiguous"]
    reason: str = Field(max_length=240)


class PageVerification(StrictModel):
    verdicts: list[Verdict] = Field(max_length=8)


class Evidence(BaseModel):
    """Canonical common fields; method and passage specifics remain inspectable."""
    model_config = ConfigDict(extra="allow", strict=True)
    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page: int | None
    section: str
    text: str = Field(min_length=1)
    content_kind: Literal["verbatim_text", "figure_transcription", "method_row", "llm_knowledge", "extracted_text"]
    evidence_scope: Scope
    revision: str = Field(min_length=1)
    validation_status: Literal["passed", "flagged"]
    human_review_status: Literal["not_reviewed", "verified", "rejected"]
    retrieval_eligible: bool
    issues: list[str]
