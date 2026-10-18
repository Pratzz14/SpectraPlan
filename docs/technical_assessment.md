# Validated technical assessments

`POST /api/assess` runs fresh customer extraction, context-aware retrieval and structured synthesis. It returns a validated assessment or an inspectable incomplete run. Scientific conclusions remain conditional: schema and provenance checks do not establish spectroscopy performance, equipment compatibility or clinical readiness.

## API and Python interface

```http
POST /api/assess
Content-Type: application/json

{"description": "Customer enquiry text", "fact_overrides": null}
```

The default description limit is 8,000 characters (`ASSESSMENT_MAX_DESCRIPTION_CHARS`, configurable up to the extraction limit of 20,000). Empty, whitespace-only, oversized, wrong-type and unknown-field requests return 422. Original whitespace is preserved for quote matching. `fact_overrides` may be omitted or null; non-null corrections are rejected. Edit the original enquiry and resubmit to obtain fresh facts, evidence and results.

The response is `AssessmentRun` with `run_status`, `facts`, `retrieval`, `assessment`, `errors`, `metadata` and `warnings`. A complete run requires validated facts, retrieval and assessment, with no errors. An incomplete run always has `assessment=null`, at least one failed-stage error and only successfully validated earlier outputs. The retrieved ledger includes the full text, source scope, revision, hash, locators, review labels, workbook notes and transcription metadata needed to inspect every citation offline. Export this actual envelope.

| Condition | HTTP | Envelope |
|---|---|---|
| Complete provisional, insufficient-information or outside-scope assessment | 200 | `run_status="complete"` |
| Retrieval or synthesis fails after validated extraction | 200 | `run_status="incomplete"`; facts retained |
| Provider/corpus unavailable without useful validated facts | 503 | Incomplete |
| Timeout without validated facts | 504 | Incomplete |
| Invalid upstream output after content repair is exhausted, without validated facts | 502 | Incomplete |
| Invalid request | 422 | Input-validation error |

Each run error identifies `code`, `stage`, sanitized `message` and the underlying `http_status`. Error stages are extraction, retrieval and synthesis. Raw invalid output and provider bodies are excluded. Unexpected programming exceptions remain server failures (500), rather than becoming technical recommendations.

```python
from backend.agent import assess_case
from backend.config import Settings
from backend.retrieval import CaseRetrievalService

settings = Settings()
result = await assess_case(description, settings,
                           retrieval_service=CaseRetrievalService(settings))
if result.run_status == "complete":
    assessment = result.assessment
else:
    failed_stage = result.errors[0].stage
```

Keep the retrieval service across requests to reuse its local embedding model. `assess_case` accepts an injected provider, an absolute monotonic deadline and an optional synchronous `on_stage(name, value)` callback after successful stage validation. F06 changes its return type from the F05 `DevelopmentAssessmentResult` to `AssessmentRun`; expected runtime failures now produce incomplete envelopes instead of propagating. Invalid caller input and unexpected programming errors still raise.

`synthesize_assessment(facts, retrieval, ...)` remains a lower-level interface returning `Assessment`. It validates the supplied objects and permits one synthesis repair, then raises on failure. Direct callers are responsible for retaining the original description and authenticating their ledger. The full pipeline revalidates extraction against the description and authenticates every retrieved record against its pinned published corpus generation before synthesis.

## Feasibility study and provenance

Recommendations distinguish method, high-level geometry, proposed location and conditional status. Unknown configuration coverage remains null with an explanation. Nominal method bands, configuration bands, Raman excitation and Raman shift are separate. Numerical coverage requires method-labeled source support; configuration coverage additionally requires an exact structured `equipment` fact with a `spectral_range` quantity. A familiar nominal band cannot become a verified hardware specification.

Technical assertion text remains selected from bounded normalized source excerpts or explicit gaps. Local checks verify excerpt identity and supporting IDs. They cannot establish that an excerpt is relevant to the selected method, geometry or customer material. Python renders the customer summary from validated extracted values; source-study equipment cannot be imported into it. Decision reasons, assumptions, questions and study prose still require semantic source review.

The experiment preserves model-proposed objectives, representative samples and reference-measurement details. `variation` explicitly identifies variation to cover. Python labels the proposal text, orders individual-method comparisons before combinations and requires reference location/time alignment. Comparisons are scoped to the methods proposed for each stream; combinations are retained only if they improve the customer decision on independent material.

Python supplies `validation_groups`, each with context IDs, `independent_unit` (batch, run, specimen, patient or unresolved) and `study_type` (targeted feasibility or characterization). Related scans stay together. Patient grouping takes precedence over within-patient specimens; ambiguous ownership remains unresolved. Contexts without a named target begin with quality-variable agreement and independent characterization before analyte calibration or exact configuration selection.

`acceptance_criteria` copies raw customer error/response-time requirements with their original fact pointers. Unstated bias, robustness and other thresholds remain null/unknown and appear in `open_items`. Python constructs the go/no-go wording; it does not invent threshold values or infer numerical requirements from model prose. `proposed_settings` contains optional finite numeric experimental choices with context IDs, name, value, units and `origin="proposed"`; these are not factual requirements or measured results.

Customer requirements use exact input quotes and JSON Pointer provenance. Python constructs `source_index` from the union of final citations, preserving workbook row and underlying PDF-table locations. `retrieval` contains every cited full evidence record, capped at eight records including method rows.

## Mechanical checks, repair and limits

`backend/validation.py` checks required structures, unique references, context ownership, complete fact provenance, quoted values, source quantities and canonical corpus records. Eligibility means passed source validation, retrieval eligibility, non-business scope and no rejected review; `human_review_status="not_reviewed"` remains accurately labeled. Automated checks are not independent human review or AFS approval.

The finite configured conflicts are:

| Rule | Mechanical boundary |
|---|---|
| `cross_context_reference` | Scoped assertions cannot borrow another stream's retrieved support |
| `method_interval_mismatch` | A coverage interval needs method-labeled support in its cited records |
| `nominal_range_as_configuration` | Configuration coverage needs structured equipment-range provenance |
| `excitation_as_coverage` | Excitation-only data cannot establish coverage |
| `threshold_override` | Customer acceptance values cannot be replaced by proposed thresholds |

These checks do not prove arbitrary prose entailment or detect every unsupported scientific claim. Source comparison is still required.

Extraction and synthesis each permit one separate content repair. Synthesis repair receives specific validation errors with identical facts, evidence and request-bound schema. It does not perform another retrieval. Authentication failures, quota exhaustion, unavailable services, corrupt evidence and timeouts bypass content repair. Transport retries remain separate and bounded.

Defaults are 30 seconds per provider call, 90 seconds for the entire request, two transport retries in pinned mode (one payload attempt per provider in automatic mode), eight evidence records and at most one additional retrieval search. All attempts, backoff, retrieval, validation and repair consume the same absolute deadline. Stage completion checks reject late output. Retrieval runs in a worker thread; the HTTP await is bounded, although an already-running native operation cannot be forcibly stopped. Its worker retains/releases its own search lock, and late results cannot replace the returned envelope.

The [shared provider configuration](providers.md) defaults to automatic LLMTech/Groq selection with synthetic availability checks and cached failover. Metadata records the actual provider/model per stage and sanitized probe/payload attempts.

Metadata exists for complete and incomplete runs: configured/returned model identities, prompt/schema hashes, pipeline/corpus/retrieval versions, stage timings, repair counts and effective limits. Corpus/retrieval versions are null until an authenticated retrieval completes. Token usage describes each stage's last successful structured call, not aggregate billing across retries and repairs. The prompt version is `synthesis-v10`, pipeline `assessment-v4`.

## Verification

Local contract tests cover successful D01/D02 fixtures, empty shortlists, undefined targets, grouping, thresholds, canonical-record tampering, malformed JSON, exhausted repair, unavailable infrastructure and deadlines. Provider calls in these tests are mocked; these are not live scientific results.

The diagnostic runner can invoke the actual public route in-process while using live provider calls and local retrieval:

```powershell
.\.venv\Scripts\python.exe -m backend.smoke_assessment --api --request-deadline-s 90 --call-timeout-s 30
```

It defaults to D01/D02 and saves timestamped records under `outputs/assessment/`. IDs remain runner bookkeeping and never enter model inputs. `--case` selects cases; `--provider` is a run-only override. Without explicit timeout arguments the diagnostic runner uses its existing 180-second total / 60-second call limits. Routine runs are ignored by Git; reviewed records can be retained explicitly.

The [F06 verification receipt](../outputs/assessment/f06_review.json) records **236 passing backend tests** and [live D01/D02 API envelopes](../outputs/assessment/20261018T031435Z_573cc337a2c7459cb0d31246fe0eebfe.json). LLMTech completed both at the standard 90-second request / 30-second call limits: about 26 seconds for D01 and 23 seconds for D02. Both return complete provisional assessments; D02 used one extraction repair and neither required synthesis repair. Agent comparison checked cited passages/rows, workbook scope, original source hashes, customer provenance and experiment design. Mechanical success and agent source comparison do not constitute independent scientific validation. Browser verification is outside F06. The [live undefined-target check](../outputs/assessment/f06_live_gap.json) also returned HTTP 200 with a complete insufficient-information assessment, an empty shortlist/source index and useful initial characterization questions, in about 8 seconds without repair. This confirms a scientific evidence gap is distinct from an incomplete infrastructure failure. Local API tests and [mocked demonstrations](../outputs/assessment/f06_mocked_api.json) cover the failure contracts. Historical F05 results remain in [review.json](../outputs/assessment/review.json).
