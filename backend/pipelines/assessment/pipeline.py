"""Attributed extraction and evidence-grounded development assessments."""

from backend.prompts import load_prompt

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, get_origin
from uuid import uuid4

from pydantic import Field, create_model, model_validator

from backend.core.config import Settings
from backend.schemas.models import (
    Assessment, AssessmentContent, AssessmentMetadata, CaseFacts, CustomerStatement,
    AssessmentRun, AssessmentRequest, ExperimentDraft, RunError, ExtractionRequest, FactModel, FactProvenance,
    MeasurementContext, Requirement, Requirements, SourceReference, Text,
)
from backend.providers.provider import Provider, ProviderError
from backend.schemas.retrieval_models import RetrievalResult
from backend.pipelines.assessment.validation import (
    ExtractionValidationError, AssessmentValidationError, validate_extraction,
    _assertion_choices, _method_choices, _validation_options, _spectral_intervals,
    _check_synthesis_inputs, _cited_ids, validate_synthesis, validate_final, authenticate_ledger,
    validation_groups, acceptance_criteria, customer_summary, canonical_source_quote,
)

EXTRACTION_PROMPT_VERSION = "extraction-v7"
EXTRACTION_PROMPT = load_prompt("assessment_extraction.txt")


def _require_properties(node):
    """Derive a strict provider schema without sacrificing safe local defaults."""
    if isinstance(node, dict):
        node.pop("default", None)
        if "properties" in node:
            node["required"] = list(node["properties"])
        for value in node.values():
            _require_properties(value)
    elif isinstance(node, list):
        for value in node:
            _require_properties(value)


def _check_required(value, node, root, path=""):
    if "$ref" in node:
        node = root["$defs"][node["$ref"].rsplit("/", 1)[1]]
    # Nullable nested objects still need all their properties when present.
    for variant in node.get("anyOf", []):
        if variant.get("type") != "null":
            _check_required(value, variant, root, path)
    if isinstance(value, dict) and "properties" in node:
        for name, child in node["properties"].items():
            if name not in value:
                raise ValueError(f"Missing required property {path}/{name}")
            _check_required(value[name], child, root, f"{path}/{name}")
    elif isinstance(value, list) and "items" in node:
        for i, item in enumerate(value):
            _check_required(item, node["items"], root, f"{path}/{i}")


class QuotedText(FactModel):
    value: Text
    input_quote: Text


class QuotedNumber(FactModel):
    value: float = Field(ge=0)
    input_quote: Text


def _extraction_context_model():
    """Derive quoted wire fields from the public context contract."""
    fields = {}
    for name, field in MeasurementContext.model_fields.items():
        if name in {"context_id", "missing_information"}:
            fields[name] = (field.annotation, field)
        elif get_origin(field.annotation) is list:
            fields[name] = (list[QuotedText], Field(description=field.description))
        elif name == "label":
            fields[name] = (QuotedText, Field(description=field.description))
        elif name == "response_time_s":
            fields[name] = (QuotedNumber | None, Field(description="Exact explicitly stated seconds only; otherwise null"))
        else:
            fields[name] = (QuotedText | None, Field(description=field.description))
    return create_model("ExtractionContext", __base__=FactModel, **fields)


ExtractionContext = _extraction_context_model()


class ExtractionOutput(FactModel):
    """Quoted model output; Python supplies the public provenance pointers."""

    contexts: list[ExtractionContext]
    customer_claims_and_requests: list[CustomerStatement]
    shared_constraints: list[QuotedText]
    missing_information: list[Text]

    def to_facts(self, description: str | None = None) -> CaseFacts:
        def source_quote(quote: str) -> str:
            if description is None:
                return quote
            return canonical_source_quote(description, quote) or quote

        contexts = []
        provenance = []
        for i, context in enumerate(self.contexts):
            values = {}
            for name in MeasurementContext.model_fields:
                value = getattr(context, name)
                if name in {"context_id", "missing_information"} or value is None:
                    values[name] = value
                elif isinstance(value, list):
                    values[name] = [item.value for item in value]
                    for j, item in enumerate(value):
                        provenance.append(FactProvenance(field_path=f"/contexts/{i}/{name}/{j}",
                                                         context_ids=[context.context_id], input_quote=source_quote(item.input_quote)))
                else:
                    values[name] = value.value
                    provenance.append(FactProvenance(field_path=f"/contexts/{i}/{name}",
                                                     context_ids=[context.context_id], input_quote=source_quote(value.input_quote)))
            contexts.append(MeasurementContext.model_validate(values))
        for i, item in enumerate(self.shared_constraints):
            provenance.append(FactProvenance(field_path=f"/shared_constraints/{i}", input_quote=source_quote(item.input_quote)))
        statements = [
            statement.model_copy(update={"input_quote": source_quote(statement.input_quote)})
            for statement in self.customer_claims_and_requests
        ]
        return CaseFacts(contexts=contexts, customer_claims_and_requests=statements,
                         shared_constraints=[item.value for item in self.shared_constraints],
                         missing_information=self.missing_information, fact_provenance=provenance)

    @classmethod
    def model_json_schema(cls, **kwargs):
        schema = super().model_json_schema(**kwargs)
        _require_properties(schema)
        return schema

    @model_validator(mode="before")
    @classmethod
    def require_all_properties(cls, value):
        schema = cls.model_json_schema()
        _check_required(value, schema, schema)
        return value


def recover_extraction_fields(output: ExtractionOutput, description: str):
    """Keep source-backed wording; omit unsupported optional fields individually."""
    data = output.model_dump()
    warnings = []

    def recover(item, path):
        quote = canonical_source_quote(description, item["input_quote"])
        if quote is None:
            warnings.append(f"Extraction warning: omitted {path}; its supporting quote could not be verified.")
            return None
        item["input_quote"] = quote
        if isinstance(item["value"], str) and canonical_source_quote(quote, item["value"]) is None:
            # Store the actual customer wording, preserving numbers, units and
            # negation rather than trying to judge a paraphrase's entailment.
            item["value"] = quote
            warnings.append(f"Extraction warning: used original customer wording for {path} instead of the model paraphrase.")
        return item

    for i, context in enumerate(data["contexts"]):
        for name, value in list(context.items()):
            path = f"/contexts/{i}/{name}"
            if isinstance(value, dict) and name != "label":
                context[name] = recover(value, path)
            elif isinstance(value, list) and name != "missing_information":
                context[name] = [kept for j, item in enumerate(value)
                                 if (kept := recover(item, f"{path}/{j}")) is not None]
    data["shared_constraints"] = [kept for i, item in enumerate(data["shared_constraints"])
                                  if (kept := recover(item, f"/shared_constraints/{i}")) is not None]
    statements = []
    for i, item in enumerate(data["customer_claims_and_requests"]):
        quote = canonical_source_quote(description, item["input_quote"])
        if quote is None:
            warnings.append(f"Extraction warning: omitted /customer_claims_and_requests/{i}; its supporting quote could not be verified.")
        else:
            item["input_quote"] = quote
            statements.append(item)
    data["customer_claims_and_requests"] = statements
    data["missing_information"].extend(warnings)
    return ExtractionOutput.model_validate(data), warnings


async def extract_case(description: str, settings: Settings | None = None, *,
                       provider: Provider | None = None, deadline: float | None = None) -> CaseFacts:
    """Extract and validate, with at most one repair sharing the initial deadline."""
    ExtractionRequest(description=description)
    config = settings if settings is not None else (provider.settings if provider is not None else Settings())
    adapter = provider if provider is not None else Provider(config)
    stop_at = min(deadline if deadline is not None else float("inf"), time.monotonic() + config.request_deadline_s)
    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": json.dumps({"description": description}, ensure_ascii=False)},
    ]
    if not hasattr(adapter, "repair_counts"):
        adapter.repair_counts = {}
    adapter.repair_counts["extraction"] = 0
    repair_errors = []
    last_content = ""
    for attempt in range(2):
        if time.monotonic() >= stop_at:
            raise ProviderError("provider_timeout", "Extraction deadline expired.", 504)
        try:
            output = await adapter.structured(
                messages, ExtractionOutput, deadline=stop_at,
                max_completion_tokens=min(config.extraction_max_completion_tokens, config.provider_max_completion_tokens),
            )
            output, recovery_warnings = recover_extraction_fields(output, description)
            facts = output.to_facts(description)
            validate_extraction(facts, description)
            if recovery_warnings:
                adapter.extraction_warnings = recovery_warnings
                if hasattr(adapter, "emit"):
                    adapter.emit("extraction_recovered", {"warnings": recovery_warnings})
            return facts
        except ExtractionValidationError as error:
            feedback = error.errors
            previous = output.model_dump_json()
        except ProviderError as error:
            generated_json_rejected = (error.code == "provider_request_rejected"
                                       and error.upstream_code == "json_validate_failed")
            if error.code != "provider_invalid_response" and not generated_json_rejected:
                if attempt:
                    error.validation_errors = repair_errors
                    error.invalid_content = last_content
                raise
            feedback = ["Response must be complete JSON with every schema property explicitly present and correct types."]
            feedback.extend(getattr(error, "validation_errors", []))
            previous = getattr(error, "invalid_content", "")
            if not isinstance(previous, str):
                previous = ""
        if hasattr(adapter, "reject_stage"):
            fallback = adapter.reject_stage(feedback, exhausted=bool(attempt))
            if attempt and fallback:
                return await extract_case(description, config, provider=adapter, deadline=stop_at)
        if attempt:
            failure = ProviderError("extraction_invalid_response", "Extraction failed schema or input-provenance validation after one repair.", 502)
            # Available only to an explicit local diagnostic runner, never the HTTP response.
            failure.validation_errors = feedback
            failure.invalid_content = previous
            raise failure
        adapter.repair_counts["extraction"] = 1
        repair_errors = feedback
        last_content = previous
        if getattr(adapter, "current_settings", config).provider_name == "llmtech" and previous:
            messages.append({"role": "assistant", "content": previous})
        # Regenerate against the original input plus exact errors. Replaying the full
        # invalid response can exceed the provider's input-token limit on repair.
        messages.append({"role": "user", "content": json.dumps({
            "validation_errors": feedback,
            "instruction": load_prompt("extraction_repair.txt"),
        })})
    raise AssertionError("Unreachable extraction state")


SYNTHESIS_PROMPT_VERSION = "synthesis-v11"
PIPELINE_VERSION = "assessment-v7"
SYNTHESIS_PROMPT = load_prompt("assessment_synthesis.txt")


class SynthesisOutput(AssessmentContent):
    """Model-authored portion; provenance and source locations come from Python."""

    experiment: ExperimentDraft

    unknowns: list[Text] = Field(default_factory=list, description=(
        "Additional consequential unknowns only; Python already retains all extraction missing_information. "
        "Do not repeat or rephrase existing unknowns; include a context label when applicable."))

    @classmethod
    def model_json_schema(cls, **kwargs):
        schema = super().model_json_schema(**kwargs)
        _require_properties(schema)
        return schema

    @model_validator(mode="before")
    @classmethod
    def require_all_properties(cls, value):
        schema = cls.model_json_schema()
        _check_required(value, schema, schema)
        return value


def synthesis_output_model(facts: CaseFacts, retrieval: RetrievalResult) -> type[SynthesisOutput]:
    """Constrain provider references to this request, in addition to local checks."""
    allowed = {"context_ids": sorted(c.context_id for c in facts.contexts),
               "evidence_ids": sorted(entry.evidence.evidence_id for entry in retrieval.evidence)}
    choices = _assertion_choices(facts, retrieval)
    methods = _method_choices(retrieval)
    validation_options = _validation_options(facts)
    if not any(text.startswith("Source excerpt (") for text in choices):
        methods = []
    bands = _spectral_intervals(retrieval, methods)
    intervals = sorted({interval for values in bands.values() for interval in values})

    def quantity_available(pattern):
        return any(support and re.fullmatch(pattern, text) for text, support in choices.items())

    def bind(node):
        if isinstance(node, dict):
            properties = node.get("properties", {})
            if "evidence_ids" in properties and "text" in properties and "kind" not in properties:
                pattern = properties["text"].get("pattern")
                if pattern:
                    values = [text for text, support in choices.items() if support and re.fullmatch(pattern, text)]
                elif properties["evidence_ids"].get("minItems", 0):
                    from backend.services.search.retrieval import _methods
                    values = [text for text in choices if text.startswith("Source excerpt (") and _methods(text)]
                else:
                    values = [text for text, support in choices.items() if not support or text.startswith("Source excerpt (")]
                    if node.get("title") in {"LimitationAssertion", "AssessmentRisk"}:
                        values = [text for text in values if not choices[text] or re.search(
                            r"\b(?:weak|sensitive|fails?|cannot|limited|limitations?|less|interference|overlap\w*|cost|calibrat\w*)\b", text, re.I)]
                if values:
                    properties["text"]["enum"] = sorted(values)
            if "method" in properties:
                if methods:
                    properties["method"]["enum"] = methods
                if not intervals:
                    properties["spectral_range"] = {"$ref": "#/$defs/UndeterminedSpectralRange"}
            if node.get("title") == "DeterminedSpectralRange" and intervals:
                properties["interval"]["enum"] = intervals
            if "recommendations" in properties and not methods:
                # Do not leave an impossible required child schema under an empty array:
                # some constrained-decoding compilers reject even unreachable children.
                properties["recommendations"]["maxItems"] = 0
                properties["recommendations"]["items"] = {"type": "string"}
            elif "recommendations" in properties:
                properties["recommendations"]["maxItems"] = min(3, len(methods) * max(1, len(facts.contexts)))
            if "raman_excitation" in properties:
                from backend.schemas.models import RamanExcitation, RamanShift
                for name, quantity_type in (("raman_excitation", RamanExcitation), ("raman_shift", RamanShift)):
                    pattern = quantity_type.model_json_schema()["properties"]["text"]["pattern"]
                    if not quantity_available(pattern):
                        properties[name] = {"type": "null", "description": "No corresponding source quantity was supplied"}
            if "validation" in properties:
                properties["validation"]["enum"] = validation_options
            if "case_summary" in properties:
                properties["case_summary"]["enum"] = [customer_summary(facts)]
            for name, field in node.get("properties", {}).items():
                if name in allowed:
                    if allowed[name]:
                        field["items"]["enum"] = allowed[name]
                    elif not field.get("minItems", 0):
                        field["maxItems"] = 0
            for value in node.values():
                bind(value)
        elif isinstance(node, list):
            for value in node:
                bind(value)

    class BoundSynthesisOutput(SynthesisOutput):
        @classmethod
        def model_json_schema(cls, **kwargs):
            schema = super().model_json_schema(**kwargs)
            bind(schema)
            # Remove unused quantity/recommendation definitions after selecting null
            # or an empty shortlist, preserving satisfiable provider grammars.
            definitions = schema.get("$defs", {})
            needed = set()

            def collect(node):
                if isinstance(node, dict):
                    if "$ref" in node:
                        name = node["$ref"].rsplit("/", 1)[1]
                        if name not in needed:
                            needed.add(name)
                            collect(definitions[name])
                    for name, child in node.items():
                        if name != "$defs":
                            collect(child)
                elif isinstance(node, list):
                    for child in node:
                        collect(child)

            collect(schema)
            schema["$defs"] = {name: value for name, value in definitions.items() if name in needed}
            return schema

    return BoundSynthesisOutput


def _assemble_experiment(data, facts):
    """Assemble guardrails while retaining detailed, explicitly proposed study content."""
    experiment = data["experiment"]
    groups = validation_groups(facts)
    experiment["validation_groups"] = groups
    criteria = acceptance_criteria(facts)
    experiment["acceptance_criteria"] = criteria
    comparisons = []
    for context in facts.contexts:
        candidates = list(dict.fromkeys(rec["method"] for rec in data["recommendations"]
                         if context.context_id in rec["context_ids"]))
        comparisons.extend(f"Proposed ({context.context_id}): evaluate {method} individually against aligned independent laboratory reference measurements."
                           for method in candidates)
        if len(candidates) > 1:
            comparisons.append(f"Proposed ({context.context_id}): retain a combined model only if it improves the client-defined decision on independent material over the individual methods.")
    if not comparisons:
        comparisons = ["Proposed: agree measurable quality variables and independent reference characterization before selecting candidate methods."]
    experiment["comparisons"] = comparisons
    experiment["measurements"].append(
        "Proposed: pair spectra and independent laboratory references at aligned sample locations and times; confirm assay identity, uncertainty and sampling lag with the customer.")
    experiment["validation"] = " ".join(
        f"Proposed ({','.join(group['context_ids'])}): keep related scans together and hold out entire independent {group['independent_unit']} units for evaluation."
        if group["independent_unit"] != "unresolved" else
        f"Proposed ({','.join(group['context_ids'])}): agree the independent experimental unit, keep related spectra together and hold out entire independent units for evaluation."
        for group in groups) or "Proposed: agree independent experimental units before testing."
    open_items = experiment["open_items"]
    for group in groups:
        cid = group["context_ids"][0]
        if group["independent_unit"] == "unresolved":
            open_items.append(f"{cid}: agree the independent experimental unit before splitting data.")
        if group["study_type"] == "characterization":
            experiment["measurements"].append(f"{cid}: agree quality variables and independently characterize representative acceptable/off-specification material before analyte calibration or exact configuration selection.")
            open_items.append(f"{cid}: clarify the target and independent characterization/reference method.")
    known = [f"{c['context_id']} {c['metric']}: {c['threshold']} (customer requirement {c['requirement_path']})"
             for c in criteria if c["origin"] == "customer"]
    known.extend(f"Case-wide customer constraint: {value} (customer requirement /shared_constraints/{i})"
                 for i, value in enumerate(facts.shared_constraints))
    for criterion in criteria:
        if criterion["origin"] == "unknown":
            open_items.append(f"{criterion['context_id']}: agree {criterion['metric']} acceptance threshold with the customer.")
    experiment["decision_criteria"] = (
        "Go/no-go proposal: proceed only if evaluation on independent material meets agreed customer-defined error, bias, response time and robustness criteria"
        + (". Stated requirements and constraints: " + "; ".join(known) if known else "")
        + ". Missing thresholds remain open; inconclusive results require clarification or further characterization.")
    for field in ("objective", "decision_criteria"):
        experiment[field] = "Proposed: " + experiment[field].removeprefix("Proposed: ")
    for field in ("samples", "measurements", "variation"):
        experiment[field] = list(dict.fromkeys("Proposed: " + text.removeprefix("Proposed: ") for text in experiment[field]))
    experiment["open_items"] = list(dict.fromkeys(open_items))


def _requirements(facts: CaseFacts, unknowns: list[str]) -> Requirements:
    """Copy customer values/quotes; never ask the synthesizer to reproduce them."""
    stated = []
    data = facts.model_dump()
    for record in facts.fact_provenance:
        parts = record.field_path.split("/")[1:]
        try:
            value = data
            for part in parts:
                if isinstance(value, list):
                    if not part.isdecimal():
                        raise ValueError
                    value = value[int(part)]
                else:
                    value = value[part]
            if not parts or not isinstance(value, (str, float, int)) or isinstance(value, bool):
                raise ValueError
            if parts[0] == "contexts":
                expected_context = facts.contexts[int(parts[1])].context_id
                if record.context_ids != [expected_context] or len(parts) < 3:
                    raise ValueError
                field = parts[2]
            elif parts[0] == "shared_constraints" and not record.context_ids:
                expected_context, field = None, "shared_constraints"
            else:
                raise ValueError
            from backend.pipelines.assessment.validation import canonical_source_quote
            if isinstance(value, str) and canonical_source_quote(record.input_quote, value) is None:
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise AssessmentValidationError(["Invalid extracted fact-provenance pointer or value"]) from None
        stated.append(Requirement(context_id=expected_context, field=field, field_path=record.field_path,
                                  value=str(value), input_quote=record.input_quote))
    missing = list(facts.missing_information)
    for context in facts.contexts:
        missing.extend(f"{context.label} ({context.context_id}): {text}" for text in context.missing_information)
    return Requirements(stated=stated, unknowns=list(dict.fromkeys([*missing, *unknowns])))


def _source_index(cited: set[str], retrieval):
    references = []
    for entry in retrieval.evidence:
        e = entry.evidence
        if e.evidence_id not in cited:
            continue
        sheet, row = getattr(e, "sheet", None), getattr(e, "row", None)
        citation = f"{e.source_id} p.{e.page}" if e.page is not None else e.source_id
        if e.content_kind == "method_row":
            citation = f"{e.source_id} {sheet} row {row}"
            underlying = getattr(e, "underlying_citation", None)
            if underlying:
                citation += f" ({underlying['source_id']} {underlying['table']} p.{underlying['page']})"
        references.append(SourceReference(evidence_id=e.evidence_id, citation=citation,
            source_id=e.source_id, file_name=e.file_name, source_sha256=e.source_sha256,
            page=e.page, sheet=sheet, row=row, revision=e.revision,
            corpus_version=e.corpus_version, evidence_url=e.evidence_url))
    return references


async def synthesize_assessment(facts: CaseFacts, retrieval: RetrievalResult, settings: Settings | None = None, *,
                                provider: Provider | None = None, deadline: float | None = None) -> Assessment:
    """Validate synthesis with one content repair over the same evidence and deadline."""
    _check_synthesis_inputs(facts, retrieval)
    requirements = _requirements(facts, [])
    config = settings if settings is not None else (provider.settings if provider is not None else Settings())
    adapter = provider if provider is not None else Provider(config)
    adapter.repair_counts["synthesis"] = 0
    stop_at = min(deadline if deadline is not None else float("inf"), time.monotonic() + config.request_deadline_s)
    payload = {
        "facts": facts.model_dump(), "corpus_version": retrieval.corpus_version,
        "evidence": [{"record": entry.evidence.model_dump(), "context_ids": entry.context_ids,
                      "facets": entry.facets} for entry in retrieval.evidence],
        "coverage": [item.model_dump() for item in retrieval.coverage],
        "gaps": [item.model_dump() for item in retrieval.gaps], "warnings": retrieval.warnings,
    }
    response_model = synthesis_output_model(facts, retrieval)
    messages = [{"role": "system", "content": SYNTHESIS_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    for attempt in range(2):
        if time.monotonic() >= stop_at:
            raise ProviderError("provider_timeout", "Assessment deadline expired.", 504)
        try:
            output = await adapter.structured(messages, response_model, deadline=stop_at,
                max_completion_tokens=min(config.synthesis_max_completion_tokens, config.provider_max_completion_tokens),
                temperature=0)
            if time.monotonic() >= stop_at:
                raise ProviderError("provider_timeout", "Assessment deadline expired.", 504)
            data = output.model_dump()
            validate_synthesis(data, facts, retrieval)
            break
        except AssessmentValidationError as error:
            feedback = error.errors
            previous = output.model_dump_json()
        except ProviderError as error:
            generated_rejection = error.code == "provider_request_rejected" and error.upstream_code == "json_validate_failed"
            if error.code != "provider_invalid_response" and not generated_rejection:
                raise
            feedback = [load_prompt("schema_repair.txt")]
            feedback.extend(getattr(error, "validation_errors", []))
            previous = getattr(error, "invalid_content", "")
        if hasattr(adapter, "reject_stage"):
            fallback = adapter.reject_stage(feedback, exhausted=bool(attempt))
            if attempt and fallback:
                return await synthesize_assessment(facts, retrieval, config, provider=adapter, deadline=stop_at)
        if attempt:
            failure = ProviderError("synthesis_invalid_response", "Synthesis failed validation after one repair.", 502)
            failure.validation_errors = feedback
            failure.invalid_content = previous
            raise failure
        if time.monotonic() >= stop_at:
            raise ProviderError("provider_timeout", "Assessment deadline expired before repair.", 504)
        adapter.repair_counts["synthesis"] = 1
        messages.append({"role": "user", "content": json.dumps({
            "validation_errors": feedback,
            "instruction": load_prompt("assessment_repair.txt"),
        }, ensure_ascii=False)})
    requirements.unknowns = _requirements(facts, data.pop("unknowns")).unknowns
    data["case_summary"] = customer_summary(facts)
    for rec in data["recommendations"]:
        spectral = rec["spectral_range"]
        if spectral["kind"] == "undetermined":
            spectral["text"] = "Coverage interval is undetermined for the proposed configuration; usable equipment coverage remains unverified."
        else:
            label = "Nominal method interval" if spectral["kind"] == "nominal_method_range" else "Source-specific configuration interval"
            spectral["text"] = f"{label}: {spectral['interval']}; usable coverage of the customer's equipment remains unverified."
    _assemble_experiment(data, facts)
    data["clarification_questions"].sort(key=lambda item: item["priority"])
    assessment = Assessment(**data, requirements=requirements, source_index=_source_index(_cited_ids(data), retrieval))
    validate_final(assessment, facts, retrieval)
    return assessment


async def assess_case(description: str, settings: Settings | None = None, *,
                      provider: Provider | None = None, retrieval_service=None,
                      deadline: float | None = None,
                      on_stage: Callable[[str, object], None] | None = None,
                      on_event: Callable[[dict], None] | None = None,
                      run_id: str | None = None) -> AssessmentRun:
    """The public pipeline; expected failures retain only successfully validated stages."""
    from backend.services.knowledge.knowledge_store import digest
    from backend.services.search.retrieval import CaseRetrievalService, RetrievalTimeout
    from backend.services.search.evidence import CorpusUnavailable

    config = settings if settings is not None else (provider.settings if provider is not None else Settings())
    AssessmentRequest(description=description)
    if len(description) > config.assessment_max_description_chars:
        raise ValueError("Enquiry exceeds configured description limit")
    adapter = provider if provider is not None else Provider(config)
    adapter.on_event = on_event
    adapter.repair_counts.clear()
    service = retrieval_service if retrieval_service is not None else CaseRetrievalService(config)
    stop_at = min(deadline if deadline is not None else float("inf"), time.monotonic() + config.request_deadline_s)
    run_id, generated_at = run_id or uuid4().hex, datetime.now(timezone.utc).isoformat()
    timings, usage, models, identities = {}, {}, {}, {}
    schemas = {"extraction": digest(ExtractionOutput.model_json_schema())}
    facts = retrieval = assessment = None
    errors = []
    stage = "extraction"
    started = time.monotonic()

    def check_deadline():
        if time.monotonic() >= stop_at:
            raise ProviderError("request_timeout", "Assessment request deadline expired.", 504)

    def completed(value):
        check_deadline()
        if stage != "retrieval":
            usage[stage] = dict(adapter.last_usage)
            models[stage] = adapter.last_model
        if on_stage is not None:
            on_stage(stage, value)

    def retrieve_and_authenticate():
        result = service.retrieve_case(facts, deadline=stop_at)
        check_deadline()
        authenticate_ledger(facts, result, config.corpus_dir)
        check_deadline()
        return result

    try:
        check_deadline()
        async with asyncio.timeout(max(0, stop_at - time.monotonic())):
            try:
                adapter.stage = "extraction"
                extracted = await extract_case(description, config, provider=adapter, deadline=stop_at)
                validate_extraction(extracted, description)
                completed(extracted)
                facts = extracted
            finally:
                timings[stage] = time.monotonic() - started
                models[stage] = adapter.last_model
                usage[stage] = dict(adapter.last_usage)
                identities[stage] = adapter.identity()
            stage, started = "retrieval", time.monotonic()
            try:
                from backend.services.search.retrieval import RETRIEVAL_EVENTS
                token = RETRIEVAL_EVENTS.set(on_event)
                try:
                    retrieved = await asyncio.to_thread(retrieve_and_authenticate)
                finally:
                    RETRIEVAL_EVENTS.reset(token)
                completed(retrieved)
                retrieval = retrieved
            finally:
                timings[stage] = time.monotonic() - started
            stage, started = "synthesis", time.monotonic()
            adapter.last_model, adapter.last_usage = None, {}
            adapter.stage = "synthesis"
            schemas["synthesis"] = digest(synthesis_output_model(facts, retrieval).model_json_schema())
            try:
                synthesized = await synthesize_assessment(facts, retrieval, config, provider=adapter, deadline=stop_at)
                completed(synthesized)
                assessment = synthesized
            finally:
                timings[stage] = time.monotonic() - started
                models[stage] = adapter.last_model
                usage[stage] = dict(adapter.last_usage)
                identities[stage] = adapter.identity()
    except (TimeoutError, ProviderError, CorpusUnavailable, RetrievalTimeout, ExtractionValidationError, AssessmentValidationError) as error:
        if isinstance(error, ProviderError):
            code, message, status = error.code, str(error), error.http_status
        elif isinstance(error, (TimeoutError, RetrievalTimeout)):
            code, message, status = "request_timeout", "Assessment request deadline expired.", 504
        elif isinstance(error, CorpusUnavailable):
            code, message, status = "corpus_unavailable", "Technical corpus or retrieval indexes are unavailable or failed validation.", 503
        else:
            code, message, status = f"{stage}_invalid_response", "Stage output failed mechanical validation.", 502
        errors.append(RunError(code=code, stage=stage, message=message, http_status=status))
    selected = adapter.current_settings
    metadata = AssessmentMetadata(run_id=run_id, generated_at=generated_at, pipeline_version=PIPELINE_VERSION,
        provider=selected.provider_name, model=selected.provider_model, returned_models=models,
        endpoint=selected.provider_base_url, corpus_version=retrieval.corpus_version if retrieval else None,
        retrieval_version=retrieval.retrieval_version if retrieval else None,
        prompt_versions={"extraction": EXTRACTION_PROMPT_VERSION, "synthesis": SYNTHESIS_PROMPT_VERSION},
        prompt_sha256={"extraction": digest(EXTRACTION_PROMPT.encode()), "synthesis": digest(SYNTHESIS_PROMPT.encode())},
        schema_sha256=schemas, stage_elapsed_s=timings, last_successful_call_usage=usage,
        call_timeout_s=config.provider_call_timeout_s, request_deadline_s=config.request_deadline_s,
        provider_max_retries=config.provider_max_retries, provider_max_completion_tokens=config.provider_max_completion_tokens,
        extraction_max_completion_tokens=min(config.extraction_max_completion_tokens, config.provider_max_completion_tokens),
        synthesis_max_completion_tokens=min(config.synthesis_max_completion_tokens, config.provider_max_completion_tokens),
        synthesis_temperature=0.0, repair_counts=dict(adapter.repair_counts),
        provider_mode=config.provider_name, stage_providers=identities, provider_attempts=list(adapter.attempts),
        provider_trace=list(adapter.trace_events))
    return AssessmentRun(run_status="incomplete" if errors else "complete", facts=facts, retrieval=retrieval,
        assessment=assessment, errors=errors, metadata=metadata,
        warnings=[*getattr(adapter, "extraction_warnings", []), *(retrieval.warnings if retrieval else []),
                  "Mechanical validation establishes traceability, not scientific correctness; inspect source relevance and scope.",
                  "Automated checks and agent inspection do not constitute independent human or scientific validation."])
