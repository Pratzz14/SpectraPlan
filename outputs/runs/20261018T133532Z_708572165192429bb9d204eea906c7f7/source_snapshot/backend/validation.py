"""Mechanical traceability checks, not a scientific entailment verifier."""

import re

from backend.models import CaseFacts
from backend.evidence import CorpusUnavailable, EvidenceNotFound, EvidenceRevisionMismatch, load_snapshot


CONFLICT_RULES = {
    "cross_context_reference": "A scoped assertion cannot borrow another stream's retrieved support.",
    "method_interval_mismatch": "A range must have method-labeled support in each cited record.",
    "nominal_range_as_configuration": "Configuration coverage needs structured equipment-range provenance.",
    "excitation_as_coverage": "Excitation-only source data cannot establish spectral coverage.",
    "threshold_override": "Acceptance thresholds are copied customer requirements, never model settings.",
    "method_rationale_mismatch": "A recommendation rationale must support the selected method family at the cited source scope.",
}

class ExtractionValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


CONSTRAINT_FIELDS = {"reference_assays", "process_constraints", "temperature", "pressure",
                     "response_time_raw", "response_time_s", "concentration_range", "required_error"}


def validate_extraction(facts: CaseFacts, description: str) -> None:
    """Mechanical traceability checks; these cannot prove arbitrary prose entailment."""
    errors = []
    ids = [context.context_id for context in facts.contexts]
    if len(set(ids)) != len(ids):
        errors.append("Context IDs must be unique")
    expected = {}
    for i, context in enumerate(facts.contexts):
        material_text = " ".join([context.label, context.sample_matrix or ""])
        forms = {match.group().lower(): match.group() for match in
                 re.finditer(r"\b(?:powder|slurry|liquid|gas|solid)\b", material_text, re.IGNORECASE)}
        if context.sample_phase is None and len(forms) == 1:
            stated_form = next(iter(forms.values()))
            errors.append(f"/contexts/{i}/sample_phase: material description explicitly states {stated_form!r}; extract that exact form with its source quote instead of null")
        for name, value in context.model_dump().items():
            if name in {"context_id", "missing_information"} or value is None:
                continue
            if isinstance(value, list):
                for j, item in enumerate(value):
                    expected[f"/contexts/{i}/{name}/{j}"] = (item, [context.context_id], name)
            else:
                expected[f"/contexts/{i}/{name}"] = (value, [context.context_id], name)
        if context.response_time_s is not None:
            match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:s|sec|secs|second|seconds)\s*",
                                 context.response_time_raw or "", re.IGNORECASE)
            if not match or float(match[1]) != context.response_time_s:
                errors.append(f"/contexts/{i}/response_time_s requires matching exact raw seconds; no conversions or bounds")
    for i, text in enumerate(facts.shared_constraints):
        expected[f"/shared_constraints/{i}"] = (text, [], "shared_constraints")

    def check_quote(quote, location):
        if quote not in description:
            errors.append(f"{location}: input_quote {quote!r} is not an exact substring of description; copy an actual source substring")

    seen = set()
    shared_uses = {}
    for i, record in enumerate(facts.fact_provenance):
        location = f"/fact_provenance/{i}"
        check_quote(record.input_quote, record.field_path)
        target = expected.get(record.field_path)
        if target is None:
            errors.append(f"{location}: field_path does not reference a stated fact")
            continue
        value, context_ids, name = target
        if record.field_path in seen:
            errors.append(f"{location}: duplicate fact provenance pointer")
        if record.context_ids != context_ids:
            errors.append(f"{location}: context_ids do not match field_path")
        if isinstance(value, str) and value not in record.input_quote:
            errors.append(f"{record.field_path}: stated wording must occur verbatim in input_quote; do not infer or generalize")
        if name in CONSTRAINT_FIELDS and context_ids:
            key = (name, str(value), record.input_quote)
            shared_uses.setdefault(key, set()).update(context_ids)
        seen.add(record.field_path)
    for (name, _, quote), contexts in shared_uses.items():
        if len(contexts) > 1 and description.count(quote) == 1:
            errors.append(f"{name}: one shared quote was assigned to multiple contexts; keep the shared constraint once at case level")
    for path in sorted(expected.keys() - seen):
        errors.append(f"{path}: missing fact provenance")
    for i, statement in enumerate(facts.customer_claims_and_requests):
        check_quote(statement.input_quote, f"/customer_claims_and_requests/{i}")
        if len(set(statement.context_ids)) != len(statement.context_ids) or not set(statement.context_ids) <= set(ids):
            errors.append(f"/customer_claims_and_requests/{i}: invalid context_ids")
    if errors:
        raise ExtractionValidationError(errors)



class AssessmentValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("Assessment failed basic context or evidence reference checks")
        self.errors = errors


ASSESSMENT_GAPS = (
    "Customer clarification is needed before finalizing the proposed feasibility study.",
    "Not established by this assessment: usable equipment coverage for this enquiry.",
    "Not established by this assessment: performance on the customer's exact material.",
    "Not established by this assessment: calibration transfer after changes to material or process.",
)
VALIDATION_OPTIONS = (
    "Proposed: keep repeat spectra from each batch or process run together; hold out entire independent batches or process runs for evaluation.",
    "Proposed: keep repeat spectra from each specimen together; hold out entire independent specimens for evaluation.",
    "Proposed: keep all specimens and repeat spectra from each patient together; hold out entire independent patients for evaluation.",
    "Proposed: agree the independent experimental unit, keep related spectra together, and hold out entire independent units for evaluation.",
)


def _raman_quantities(retrieval):
    """Conservative labeled quantities; an unrelated nm/MIR number is not Raman data."""
    quantities = {}
    for entry in retrieval.evidence:
        e = entry.evidence
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", " ".join(e.text.split())):
            if not re.search(r"\braman\b", sentence, re.I):
                continue
            patterns = []
            if re.search(r"\bexcitation\b", sentence, re.I):
                patterns.append(r"\b\d+(?:\.\d+)?\s*nm\b")
            if re.search(r"\bshift\b", sentence, re.I):
                patterns.append(r"\b\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?\s*cm(?:\^-?1|-1|⁻¹)\b")
            for pattern in patterns:
                for quantity in re.findall(pattern, sentence):
                    quantities.setdefault(quantity, set()).add(e.evidence_id)
    return quantities


def _assertion_choices(facts, retrieval):
    """Verbatim normalized excerpts and explicit gaps; not an entailment classifier."""
    choices = {text: set() for text in ASSESSMENT_GAPS}
    for entry in retrieval.evidence:
        e = entry.evidence
        normalized = " ".join(e.text.split())
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", normalized)
        # Bound schema size without truncating an assertion or dropping its qualifiers.
        excerpts = [sentence for sentence in sentences
                    if 35 <= len(sentence) <= 900 and len(sentence.split()) >= 5
                    and (e.content_kind == "method_row" or sentence.endswith((".", "!", "?")))][:8]
        for excerpt in excerpts:
            label = f"Source excerpt ({e.evidence_scope}): {excerpt}"
            choices.setdefault(label, set()).add(e.evidence_id)
    choices.update(_raman_quantities(retrieval))
    for context in facts.contexts:
        for unknown in context.missing_information:
            choices.setdefault(f"Open customer question for {context.context_id}: {unknown}", set())
    for unknown in facts.missing_information:
        choices.setdefault(f"Open customer question: {unknown}", set())
    return choices


def _method_choices(retrieval):
    from backend.retrieval import _methods

    labels = {"nir": "NIR", "raman": "Raman", "mir": "MIR/FTIR", "uv": "UV/Vis", "fluorescence": "Fluorescence"}
    families = set()
    for entry in retrieval.evidence:
        e = entry.evidence
        if e.content_kind == "method_row" or e.evidence_scope in {"application_example", "research_demonstration"}:
            families.update(_methods(getattr(e, "method", "") or e.text))
    return sorted(labels[family] for family in families)


def _method_rationale_errors(data, retrieval):
    """Detect an explicitly different method in a recommendation's cited rationale.

    This is deliberately a narrow conflict check. It catches a MIR/fluorescence
    excerpt attached to an NIR recommendation, while leaving broader scientific
    entailment and matrix suitability to source review.
    """
    from backend.retrieval import _methods

    labels = {"NIR": "nir", "Raman": "raman", "MIR/FTIR": "mir",
              "UV/Vis": "uv", "Fluorescence": "fluorescence"}
    entries = {entry.evidence.evidence_id: entry for entry in retrieval.evidence}
    errors = []
    for index, recommendation in enumerate(data.get("recommendations", [])):
        selected = labels.get(recommendation.get("method"))
        if selected is None:
            continue
        for evidence_id in recommendation.get("rationale", {}).get("evidence_ids", []):
            entry = entries.get(evidence_id)
            if entry is None:
                continue
            evidence = entry.evidence
            source_text = " ".join(filter(None, [getattr(evidence, "method", None), evidence.text]))
            families = _methods(source_text)
            if families and selected not in families:
                errors.append(
                    f"/recommendations/{index}/rationale/evidence_ids: method_rationale_mismatch "
                    f"(selected {recommendation['method']}; cited source identifies {', '.join(sorted(families))})"
                )
    return errors


def _validation_options(facts):
    quotes = " ".join([p.input_quote for p in facts.fact_provenance] +
                      [s.input_quote for s in facts.customer_claims_and_requests])
    units = []
    if re.search(r"\b(?:batch(?:es)?|process(?:ing)?|production|manufactur\w*|press|blend(?:ing)?|runs?)\b", quotes, re.I):
        units.append(VALIDATION_OPTIONS[0])
    if re.search(r"\b(?:specimens?|biops\w*|tissues?)\b", quotes, re.I):
        units.append(VALIDATION_OPTIONS[1])
    if re.search(r"\bpatients?\b", quotes, re.I):
        # Patient grouping takes precedence over within-patient specimen grouping.
        units = [unit for unit in units if unit != VALIDATION_OPTIONS[1]]
        units.append(VALIDATION_OPTIONS[2])
    return units if len(units) == 1 else [VALIDATION_OPTIONS[3]]


def _spectral_intervals(retrieval, methods):
    """Conservative, method-labeled bands; reject depth and excitation as coverage."""
    from backend.retrieval import _methods

    labels = {"nir": "NIR", "raman": "Raman", "mir": "MIR/FTIR", "uv": "UV/Vis", "fluorescence": "Fluorescence"}
    pattern = r"\b[0-9]+(?:\.[0-9]+)?\s*(?:-|–|—|to)\s*[0-9]+(?:\.[0-9]+)?\s*(?:nm|[uµμ]m|cm(?:\^-1|-1|⁻¹))\b"
    intervals = {method: {} for method in methods}
    for entry in retrieval.evidence:
        e = entry.evidence
        normalized = " ".join(e.text.split())
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", normalized):
            if not re.search(r"\b(?:range|band|region|coverage|spectr\w*)\b", sentence, re.I) or re.search(r"\b(?:excitation|depth|penetration)\b", sentence, re.I):
                continue
            families = _methods(sentence) or _methods(normalized)
            if len(families) != 1:
                continue
            method = labels[next(iter(families))]
            if method not in intervals:
                continue
            for interval in re.findall(pattern, sentence):
                intervals[method].setdefault(interval, set()).add(e.evidence_id)
    return intervals



def _assertion_errors(value, choices, path=""):
    errors = []
    if isinstance(value, dict):
        if "text" in value and "evidence_ids" in value and "kind" not in value:
            support = choices.get(value["text"])
            cited = set(value["evidence_ids"])
            if support is None or (support and (not cited or not cited <= support)) or (not support and cited):
                errors.append(f"{path}: use a supplied source excerpt with its supporting IDs, or an uncited explicit gap")
        for name, child in value.items():
            errors.extend(_assertion_errors(child, choices, f"{path}/{name}"))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            errors.extend(_assertion_errors(child, choices, f"{path}/{i}"))
    return errors



def _reference_errors(value, context_ids, evidence_ids, path=""):
    """Membership only: does not determine scientific support or prose attribution."""
    errors = []
    if isinstance(value, dict):
        for name, items in value.items():
            location = f"{path}/{name}"
            if name in {"context_ids", "evidence_ids"}:
                allowed = context_ids if name == "context_ids" else evidence_ids
                if len(items) != len(set(items)):
                    errors.append(f"{location}: duplicate references")
                if set(items) - allowed:
                    errors.append(f"{location}: references outside the supplied set")
            else:
                errors.extend(_reference_errors(items, context_ids, evidence_ids, location))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            errors.extend(_reference_errors(item, context_ids, evidence_ids, f"{path}/{i}"))
    return errors


def _check_synthesis_inputs(facts, retrieval):
    context_ids = {c.context_id for c in facts.contexts}
    errors = []
    if len(context_ids) != len(facts.contexts):
        errors.append("Duplicate fact context IDs")
    errors.extend(_reference_errors(facts.model_dump(), context_ids, set()))
    ids = [entry.evidence.evidence_id for entry in retrieval.evidence]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate ledger evidence IDs")
    for entry in retrieval.evidence:
        evidence = entry.evidence
        if (not evidence.retrieval_eligible or evidence.validation_status != "passed"
                or evidence.human_review_status == "rejected" or evidence.evidence_scope == "business_context"
                or evidence.issues
                or evidence.corpus_version != retrieval.corpus_version):
            errors.append("Ledger contains excluded evidence or a different corpus revision")
        errors.extend(_reference_errors(entry.model_dump(), context_ids, set(ids)))
    if errors:
        raise AssessmentValidationError(errors)




def _cited_ids(value):
    if isinstance(value, dict):
        return set(value.get("evidence_ids", [])) | set().union(*(
            _cited_ids(child) for name, child in value.items() if name != "evidence_ids"))
    if isinstance(value, list):
        return set().union(*(_cited_ids(child) for child in value))
    return set()


def authenticate_ledger(facts, retrieval, root):
    """Authenticate all retrieved records against their immutable published generation."""
    try:
        _check_synthesis_inputs(facts, retrieval)
        snapshot = load_snapshot(root, retrieval.corpus_version)
        for entry in retrieval.evidence:
            canonical = snapshot.resolve(entry.evidence.evidence_id, entry.evidence.revision)
            if canonical.model_dump() != entry.evidence.model_dump():
                raise CorpusUnavailable("Retrieved evidence differs from its published corpus record")
    except (AssessmentValidationError, EvidenceNotFound, EvidenceRevisionMismatch):
        raise CorpusUnavailable("Retrieved evidence cannot be resolved in its pinned corpus") from None


def validation_groups(facts):
    groups = []
    for context in facts.contexts:
        # Use quotes only when they do not also describe another stream. Broad
        # multi-stream quotes cannot establish which stream owns an experimental unit.
        parts = [str(v) for k, v in context.model_dump().items()
                 if k not in {"context_id", "missing_information"} and v is not None]
        parts += [s.text for s in facts.customer_claims_and_requests
                  if not s.context_ids or context.context_id in s.context_ids]
        parts += facts.shared_constraints
        own_quotes = [p.input_quote for p in facts.fact_provenance
                      if p.context_ids == [context.context_id]]
        exclusive_quotes = [quote for quote in own_quotes if not any(
            other.label in quote for other in facts.contexts if other.context_id != context.context_id)]
        parts += exclusive_quotes
        text = " ".join(parts)
        if re.search(r"\bpatients?\b", text, re.I):
            unit = "patient"
        elif re.search(r"\b(?:specimens?|biops\w*|tissues?)\b", text, re.I):
            # If patient ownership exists only in an ambiguous quote, ask rather
            # than incorrectly treating within-patient specimens as independent.
            unit = "unresolved" if any(re.search(r"\bpatients?\b", quote, re.I)
                                        for quote in own_quotes) else "specimen"
        elif re.search(r"\bbatch(?:es)?\b", text, re.I):
            unit = "batch"
        elif re.search(r"\b(?:runs?|process\w*|production|manufactur\w*|press|blend\w*)\b", text, re.I):
            unit = "run"
        else:
            unit = "unresolved"
        groups.append({"context_ids": [context.context_id], "independent_unit": unit,
                       "study_type": "targeted_feasibility" if context.target_analytes else "characterization"})
    return groups


def acceptance_criteria(facts):
    criteria = []
    for i, context in enumerate(facts.contexts):
        for metric in ("required_error", "response_time_raw", "bias", "robustness"):
            threshold = getattr(context, metric, None)
            criteria.append({"context_id": context.context_id, "metric": metric,
                "threshold": threshold, "requirement_path": f"/contexts/{i}/{metric}" if threshold else None,
                "origin": "customer" if threshold else "unknown"})
    return criteria


def customer_summary(facts):
    """Render validated customer values without importing source-study details."""
    contexts = []
    for context in facts.contexts:
        parts = [f"{context.label} ({context.context_id})"]
        for field, label in (("sample_matrix", "material"), ("sample_phase", "phase"),
                             ("appearance", "appearance"), ("temperature", "temperature"),
                             ("pressure", "pressure"), ("concentration_range", "reported concentration"),
                             ("required_error", "requested error"), ("response_time_raw", "requested response time")):
            value = getattr(context, field)
            if value is not None:
                parts.append(f"{label}: {value}")
        for field, label in (("target_analytes", "targets"), ("measurement_goals", "requested outcomes"),
                             ("reference_assays", "reported reference checks"), ("process_constraints", "stated constraints")):
            values = getattr(context, field)
            if values:
                parts.append(f"{label}: {', '.join(values)}")
        contexts.append("; ".join(parts))
    if facts.shared_constraints:
        contexts.append("Case-wide customer wording: " + "; ".join(facts.shared_constraints))
    return " ".join(". ".join(contexts).split()) if contexts else (
        "No measurement context was extracted; target and sample details require clarification.")


def validate_synthesis(data, facts, retrieval):
    """Finite structural conflicts; this does not evaluate arbitrary prose support."""
    errors = _reference_errors(data, {c.context_id for c in facts.contexts},
                               {e.evidence.evidence_id for e in retrieval.evidence})
    errors += _assertion_errors(data, _assertion_choices(facts, retrieval))
    errors += _method_rationale_errors(data, retrieval)
    entries = {e.evidence.evidence_id: e for e in retrieval.evidence}
    methods = _method_choices(retrieval)
    bands = _spectral_intervals(retrieval, methods)
    seen = set()

    def scoped(value, contexts, path):
        if isinstance(value, dict):
            contexts = value.get("context_ids", contexts)
            for eid in value.get("evidence_ids", []):
                entry = entries.get(eid)
                if entry and entry.context_ids and not set(contexts) <= set(entry.context_ids):
                    errors.append(f"{path}/evidence_ids: cross_context_reference")
            for key, child in value.items():
                scoped(child, contexts, f"{path}/{key}")
        elif isinstance(value, list):
            for i, child in enumerate(value):
                scoped(child, contexts, f"{path}/{i}")
    scoped(data, [], "")
    for i, rec in enumerate(data["recommendations"]):
        path = f"/recommendations/{i}"
        if rec["method"] not in methods:
            errors.append(f"{path}/method: choose a single supported method family")
        identity = (tuple(sorted(rec["context_ids"])), rec["method"], rec["geometry"], rec["measurement_location"])
        if identity in seen:
            errors.append(f"{path}: duplicate method/configuration for the same contexts")
        seen.add(identity)
        spectral = rec["spectral_range"]
        interval = spectral["interval"]
        if interval is not None:
            support = bands.get(rec["method"], {}).get(interval, set())
            if not spectral["evidence_ids"] or not set(spectral["evidence_ids"]) <= support:
                errors.append(f"{path}/spectral_range: method_interval_mismatch or excitation_as_coverage; interval is absent from method-labeled source coverage")
            if spectral["kind"] == "source_configuration_range":
                for eid in spectral["evidence_ids"]:
                    entry = entries.get(eid)
                    source = entry.evidence.model_dump() if entry else {}
                    equipment_ranges = [q.get("value") for f in source.get("facts", [])
                        if f.get("category") == "equipment" for q in f.get("quantities", [])
                        if q.get("kind") == "spectral_range"]
                    if interval not in equipment_ranges:
                        errors.append(f"{path}/spectral_range: nominal_range_as_configuration; structured equipment range provenance required")
    if data["experiment"]["validation"] not in _validation_options(facts):
        errors.append("/experiment/validation: select an independent-unit validation proposal")
    for i, setting in enumerate(data["experiment"]["proposed_settings"]):
        name = re.sub(r"[^a-z]+", "_", setting["name"].lower()).strip("_")
        if name in {"required_error", "acceptable_error", "acceptance_threshold", "bias", "robustness", "response_time_raw"}:
            errors.append(f"/experiment/proposed_settings/{i}: threshold_override; keep acceptance thresholds in customer criteria/open items")
    if errors:
        raise AssessmentValidationError(errors)


def validate_final(assessment, facts, retrieval):
    data = assessment.model_dump()
    errors = _reference_errors(data, {c.context_id for c in facts.contexts},
                               {e.evidence.evidence_id for e in retrieval.evidence})
    if assessment.case_summary != customer_summary(facts):
        errors.append("/case_summary: must contain only backend-rendered customer facts")
    provenance = {p.field_path: p for p in facts.fact_provenance}
    if {r.field_path for r in assessment.requirements.stated} != set(provenance):
        errors.append("/requirements/stated: missing customer provenance")
    for requirement in assessment.requirements.stated:
        original = provenance.get(requirement.field_path)
        value = facts.model_dump()
        try:
            for part in requirement.field_path.split("/")[1:]:
                value = value[int(part)] if isinstance(value, list) else value[part]
            expected_context = original.context_ids[0] if original and original.context_ids else None
            if (not original or requirement.input_quote != original.input_quote
                    or requirement.value != str(value) or requirement.context_id != expected_context):
                errors.append(f"/requirements/stated/{requirement.field_path}: customer provenance mismatch")
        except (KeyError, IndexError, ValueError, TypeError):
            errors.append("/requirements/stated: invalid customer fact pointer")
    if data["experiment"]["acceptance_criteria"] != acceptance_criteria(facts):
        errors.append("/experiment/acceptance_criteria: threshold_override")
    if data["experiment"]["validation_groups"] != validation_groups(facts):
        errors.append("/experiment/validation_groups: independent-unit or study-type conflict")
    if ({e.evidence_id for e in assessment.source_index} != _cited_ids(data)
            or len(assessment.source_index) != len(_cited_ids(data))):
        errors.append("/source_index: must contain exactly the union of final citations")
    for source in assessment.source_index:
        entry = next(e.evidence for e in retrieval.evidence if e.evidence.evidence_id == source.evidence_id)
        for name in ("source_id", "file_name", "source_sha256", "page", "sheet", "row", "revision", "corpus_version", "evidence_url"):
            if getattr(source, name) != getattr(entry, name, None):
                errors.append(f"/source_index/{source.evidence_id}/{name}: source location mismatch")
    if errors:
        raise AssessmentValidationError(errors)
