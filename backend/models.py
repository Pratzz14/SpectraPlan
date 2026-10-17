"""Customer-supplied facts, not verified spectroscopy capabilities."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
