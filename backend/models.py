"""Customer-supplied facts, not verified spectroscopy capabilities."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.retrieval_models import RetrievalResult

Text = Annotated[str, Field(min_length=1)]
StatementKind = Literal["reported_fact", "requested_outcome", "proposed_approach", "customer_claim"]


class FactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @field_validator("*")
    @classmethod
    def reject_blank(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("Text must not be blank")
        if isinstance(value, list) and any(isinstance(v, str) and not v.strip() for v in value):
            raise ValueError("List text must not be blank")
        return value


class MeasurementContext(FactModel):
    context_id: str = Field(pattern=r"^stream_[1-9][0-9]*$")
    label: Text = Field(description="One short verbatim phrase copied from the enquiry")
    target_analytes: list[Text] = Field(default_factory=list, description="Requested analytes or composition variables; populate whenever the customer names a measurement target")
    measurement_goals: list[Text] = Field(default_factory=list, description="Requested outcomes or comparisons, not bare concentration ranges")
    sample_matrix: Text | None = Field(default=None, description="Verbatim material/product description including stated components where possible")
    sample_phase: Text | None = Field(default=None, description="Explicit sample form, including powder, slurry or liquid. Copy the stated word; powder is powder, not solid. Null only when form is unstated")
    appearance: Text | None = Field(default=None, description="Verbatim stated optical appearance such as opaque, clear or turbid; otherwise null")
    temperature: Text | None = Field(default=None, description="Verbatim stated range/units or qualitative temperature wording; otherwise null")
    pressure: Text | None = Field(default=None, description="Verbatim stated pressure, including any basis/units; otherwise null")
    response_time_raw: Text | None = Field(default=None, description="Verbatim REQUESTED measurement response time, even if units are ambiguous. Existing laboratory delays are not a requested response time")
    response_time_s: float | None = Field(default=None, ge=0)
    concentration_range: Text | None = Field(default=None, description="Verbatim concentration range and any stated basis/units. Preserve a given range even when its basis is unknown; clarify basis separately")
    required_error: Text | None = Field(default=None, description="Verbatim customer error requirement and units; otherwise null")
    reference_assays: list[Text] = Field(default_factory=list)
    process_constraints: list[Text] = Field(default_factory=list)
    missing_information: list[Text] = Field(default_factory=list)


class CustomerStatement(FactModel):
    text: Text
    kind: StatementKind
    context_ids: list[Text] = Field(default_factory=list)
    input_quote: Text


class FactProvenance(FactModel):
    field_path: Text = Field(description="JSON Pointer to one stated scalar or list item, e.g. /contexts/0/sample_phase")
    context_ids: list[Text] = Field(default_factory=list)
    input_quote: Text


class CaseFacts(FactModel):
    contexts: list[MeasurementContext] = Field(default_factory=list)
    customer_claims_and_requests: list[CustomerStatement] = Field(default_factory=list)
    shared_constraints: list[Text] = Field(default_factory=list)
    missing_information: list[Text] = Field(default_factory=list)
    fact_provenance: list[FactProvenance] = Field(default_factory=list)


class ExtractionRequest(FactModel):
    # Preserve the original text, including whitespace, for quote membership checks.
    description: str = Field(min_length=1, max_length=20000)


class AssessmentRequest(FactModel):
    description: str = Field(min_length=1)
    fact_overrides: None = None

    @field_validator("description")
    @classmethod
    def nonblank_description(cls, value):
        if not value.strip():
            raise ValueError("Enter an enquiry description")
        return value


class Assertion(FactModel):
    text: Text
    evidence_ids: list[Text] = Field(default_factory=list, description=(
        "Supporting IDs from the supplied ledger. Empty only for explicit missing information, "
        "an evidence gap or a labeled proposal, never a technical capability claim."))


class SourceAssertion(Assertion):
    evidence_ids: list[Text] = Field(min_length=1)


class LimitationAssertion(Assertion):
    """A source limitation or an explicitly unverified aspect of the enquiry."""


class RamanExcitation(SourceAssertion):
    text: Text = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?\s*nm$")


class RamanShift(SourceAssertion):
    text: Text = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?\s*(?:-|–|—|to)\s*[0-9]+(?:\.[0-9]+)?\s*cm(?:\^-?1|-1|⁻¹)$")


class SpectralRange(Assertion):
    kind: Literal["nominal_method_range", "source_configuration_range", "undetermined"]
    interval: Text | None = Field(default=None, description=(
        "Actual source-backed nominal or configuration coverage interval with units; null when unavailable. "
        "A laser excitation wavelength is not a coverage interval."))
    raman_excitation: RamanExcitation | None = Field(default=None, description="Separately labeled source-backed Raman excitation wavelength, or null")
    raman_shift: RamanShift | None = Field(default=None, description="Separately labeled source-backed Raman shift coverage, or null")

    @model_validator(mode="after")
    def require_range_support(self):
        if self.kind != "undetermined" and not self.evidence_ids:
            raise ValueError("A determined spectral range requires source evidence")
        if (self.kind == "undetermined") != (self.interval is None):
            raise ValueError("Use undetermined with interval=null when no coverage interval is supplied")
        for quantity in (self.raman_excitation, self.raman_shift):
            if quantity is not None and not quantity.evidence_ids:
                raise ValueError("Raman excitation and shift values require their own source evidence")
        return self


class UndeterminedSpectralRange(SpectralRange):
    kind: Literal["undetermined"]
    interval: None


class DeterminedSpectralRange(SpectralRange):
    kind: Literal["nominal_method_range", "source_configuration_range"]
    interval: Text = Field(
        pattern=r"^[0-9]+(?:\.[0-9]+)?\s*(?:-|–|—|to)\s*[0-9]+(?:\.[0-9]+)?\s*(?:nm|[uµμ]m|cm(?:\^-?1|-1|⁻¹))$",
        description="Two source-backed numeric bounds and units, e.g. lower-upper nm or lower-upper cm^-1. A technique name is not an interval.")


class ClarificationQuestion(FactModel):
    priority: int = Field(ge=1)
    context_ids: list[Text] = Field(default_factory=list)
    question: Text
    reason: Assertion
    affects: list[Text] = Field(default_factory=list)


class Recommendation(FactModel):
    context_ids: list[Text] = Field(min_length=1)
    method: Text
    geometry: Text | None
    measurement_location: Text | None
    spectral_range: UndeterminedSpectralRange | DeterminedSpectralRange
    rationale: SourceAssertion
    assumptions: list[Text] = Field(default_factory=list)
    limitations: list[LimitationAssertion] = Field(default_factory=list)
    status: Literal["worth_testing", "conditional_on_clarification"]

    @model_validator(mode="after")
    def require_support_and_explanation(self):
        if not self.rationale.evidence_ids:
            raise ValueError("A recommendation rationale requires source evidence")
        if (self.geometry is None or self.measurement_location is None) and not self.limitations:
            raise ValueError("Unspecified geometry/location requires an explanation in limitations")
        return self


class AssessmentRisk(LimitationAssertion):
    context_ids: list[Text] = Field(default_factory=list)


class ProposedSetting(FactModel):
    context_ids: list[Text]
    name: Text
    value: float
    unit: Text | None
    origin: Literal["proposed"] = "proposed"


class ValidationGroup(FactModel):
    context_ids: list[Text]
    independent_unit: Literal["batch", "run", "specimen", "patient", "unresolved"]
    study_type: Literal["targeted_feasibility", "characterization"]


class AcceptanceCriterion(FactModel):
    context_id: Text
    metric: Literal["required_error", "response_time_raw", "bias", "robustness"]
    threshold: Text | None
    requirement_path: Text | None
    origin: Literal["customer", "unknown"]


class ExperimentDraft(FactModel):
    """Proposed study design, not measured results or confirmed requirements."""

    context_ids: list[Text] = Field(default_factory=list)
    objective: Text
    samples: list[Text] = Field(min_length=1)
    measurements: list[Text] = Field(min_length=1)
    comparisons: list[Text] = Field(default_factory=list)
    validation: Text
    decision_criteria: Text
    open_items: list[Text] = Field(default_factory=list)
    variation: list[Text] = Field(min_length=1)
    proposed_settings: list[ProposedSetting] = Field(default_factory=list)


class Experiment(ExperimentDraft):
    validation_groups: list[ValidationGroup]
    acceptance_criteria: list[AcceptanceCriterion]


class Requirement(FactModel):
    context_id: Text | None
    field: Text
    field_path: Text
    value: Text
    origin: Literal["customer"] = "customer"
    input_quote: Text


class Requirements(FactModel):
    stated: list[Requirement] = Field(default_factory=list)
    unknowns: list[Text] = Field(default_factory=list)


class SourceReference(FactModel):
    evidence_id: Text
    citation: Text
    source_id: Text
    file_name: Text
    source_sha256: Text
    page: int | None
    sheet: Text | None
    row: int | None
    revision: Text
    corpus_version: Text
    evidence_url: Text


class AssessmentContent(FactModel):
    decision_status: Literal["provisional", "insufficient_information", "outside_supported_scope"]
    decision_reason: Text
    case_summary: Text
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    risks: list[AssessmentRisk] = Field(default_factory=list)
    experiment: Experiment

    @model_validator(mode="after")
    def require_actionable_decision(self):
        if self.decision_status == "provisional" and not self.recommendations:
            raise ValueError("A provisional assessment requires a supported recommendation")
        if not self.recommendations and not self.clarification_questions:
            raise ValueError("An empty shortlist requires useful clarification questions")
        return self


class Assessment(AssessmentContent):
    requirements: Requirements
    source_index: list[SourceReference] = Field(default_factory=list)


class AssessmentMetadata(FactModel):
    run_id: Text
    generated_at: Text
    pipeline_version: Text
    provider: Text
    model: Text
    returned_models: dict[str, str | None]
    endpoint: Text
    corpus_version: Text | None
    retrieval_version: Text | None
    prompt_versions: dict[str, str]
    prompt_sha256: dict[str, str]
    schema_sha256: dict[str, str]
    stage_elapsed_s: dict[str, float]
    last_successful_call_usage: dict[str, dict[str, int]]
    call_timeout_s: float
    request_deadline_s: float
    provider_max_retries: int
    provider_max_completion_tokens: int
    extraction_max_completion_tokens: int
    synthesis_max_completion_tokens: int
    synthesis_temperature: float
    repair_counts: dict[str, int] = Field(default_factory=dict)
    provider_mode: Literal["auto", "groq", "llmtech"] = "groq"
    stage_providers: dict[str, dict] = Field(default_factory=dict)
    provider_attempts: list[dict] = Field(default_factory=list)


class DevelopmentAssessmentResult(FactModel):
    development_only: Literal[True] = True
    facts: CaseFacts
    retrieval: RetrievalResult
    assessment: Assessment
    metadata: AssessmentMetadata
    warnings: list[Text] = Field(default_factory=list)


class RunError(FactModel):
    code: Text
    stage: Literal["extraction", "retrieval", "synthesis"]
    message: Text
    http_status: Literal[502, 503, 504]


class AssessmentRun(FactModel):
    run_status: Literal["complete", "incomplete"]
    facts: CaseFacts | None
    retrieval: RetrievalResult | None
    assessment: Assessment | None
    errors: list[RunError]
    metadata: AssessmentMetadata
    warnings: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_outcome(self):
        if self.retrieval is not None and self.facts is None:
            raise ValueError("Retrieval requires validated facts")
        if self.run_status == "complete":
            if self.facts is None or self.retrieval is None or self.assessment is None or self.errors:
                raise ValueError("Complete runs require validated facts, retrieval and assessment without errors")
        elif self.assessment is not None or not self.errors:
            raise ValueError("Incomplete runs require assessment=null and a failed-stage error")
        return self
