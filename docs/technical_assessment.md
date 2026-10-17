# Development technical assessments

F05 joins customer extraction, context-aware retrieval and structured synthesis in one reusable Python pipeline. It produces a conditional technical assessment and an inspectable evidence ledger. It is a development result: the public assessment API and comprehensive validation/repair arrive in F06.

## Python interface

```python
from backend.agent import assess_case
from backend.config import Settings
from backend.retrieval import CaseRetrievalService

settings = Settings()
retrieval = CaseRetrievalService(settings)
result = await assess_case(description, settings, retrieval_service=retrieval)
```

Keep the retrieval service to reuse its local embedding model. `assess_case` performs fresh extraction, retrieves from one pinned published corpus generation and synthesizes once. It accepts an injected `Provider`, an absolute `time.monotonic()` deadline and an optional synchronous `on_stage(name, value)` callback after each successfully checked stage. Retrieval runs in a worker thread. The existing retrieval lock still serializes embedded Qdrant access; an in-progress local embedding operation cannot be forcibly interrupted, but late output is rejected.

`synthesize_assessment(facts, retrieval, settings, ...)` exposes the synthesis stage separately. It accepts typed `CaseFacts` and `RetrievalResult`; callers must retain the actual extracted input provenance and trusted retrieval result. Basic reference checks do not authenticate an arbitrary caller-created evidence object against disk. The complete pipeline obtains those objects from the existing extraction and retrieval services.

`DevelopmentAssessmentResult` contains `development_only=true`, `facts`, `retrieval`, `assessment`, `metadata` and warnings. It intentionally does not use the future public API's `run_status` contract. The scientific decision status remains independent of whether execution succeeded.

## Assessment and evidence

The assessment follows specification §6.2: decision status/reason, summary, requirements, prioritized questions, recommendations, risks, initial experiment and source index. Scientific statuses are `provisional`, `insufficient_information` and `outside_supported_scope`. A provisional result requires a supported candidate. The latter two may have an empty shortlist, with useful clarification and a proposed next investigation.

Recommendations distinguish method, geometry and proposed measurement location. Status is `worth_testing` or `conditional_on_clarification`; neither approves equipment. Unsupported geometry/location can remain null with an explanation. Assertions carry `text` and `evidence_ids`. Empty evidence lists are appropriate for explicit information/evidence gaps or labeled proposals, not technical capability claims. Context references remain attached to recommendations, questions, risks and experiments; an empty list means case-wide applicability.

Technical assertion text is conservatively selected from bounded, whitespace-normalized source excerpts or explicitly labeled gap/open-question statements, rather than freely paraphrased. Source excerpts retain their original evidence scope in the text. The request-specific provider schema enumerates the available assertions, evidence/context IDs and single method families; local checks also verify the chosen excerpt against its supporting record IDs. This prevents unsupported prose embellishments from passing merely because they carry a valid citation. It still cannot establish that the chosen excerpt is relevant to a particular method, geometry or customer matrix.

Spectral descriptions distinguish `nominal_method_range`, `source_configuration_range` and `undetermined`. The additional `interval` field must be null for an undetermined range. A determined interval requires two numeric bounds with units (`nm`, `um`/`µm` or `cm^-1`) and matching text in its cited source. Python builds its description from the selected kind and interval, preserving the distinction from usable equipment coverage. `raman_excitation` and `raman_shift` are separate nullable cited quantities. An excitation wavelength alone does not establish Raman shift coverage or usable equipment coverage.

Python constructs stated requirements from extracted fact values, exact quotes and JSON Pointer paths. Shared requirements use `context_id=null`. It retains extracted unknowns with context labels and adds further synthesis unknowns. Python also constructs `source_index` from the union of cited ledger IDs, preserving file hashes, page/sheet/row, corpus version, revision and pinned evidence URL. Method-table citations distinguish workbook rows from the underlying PDF table. Full evidence text, source scope, workbook notes and review status remain in the returned retrieval ledger and saved diagnostic record.

## Prompt and failure boundaries

The versioned synthesis prompt treats customer and document text as untrusted data. It requests conditional shortlists, focused questions, source-scoped reasoning and an initial experiment with independent references and validation by independent experimental units. It does not receive organizer worked answers or rejected search candidates. Missing numerical requirements remain open; they do not automatically prevent a screening hypothesis.

The model selects an independent-unit validation proposal. Python assembles comparisons of the selected methods individually against independent references before any proposed combination, aligns reference locations/timing, and labels the initial experiment as a proposal. Detailed sample design, feasibility criteria and broader scientific checks remain F06 work.

The provider receives a strict schema. Basic local checks reject duplicate/unknown context or evidence references, excluded or mixed-generation ledger records, unsupported assertion text, mismatched excerpt citations, unsupported range shapes/values and invalid structured fact pointers. These checks establish structure, excerpt identity and reference membership, not scientific entailment, semantic completeness or compatibility. Summary, decision reason, assumptions, questions and configuration concepts still need semantic review. Development review must compare the choices with the cited sources.

Synthesis makes one attempt, without automatic content repair or provider fallback. Extraction retains its existing single repair and the provider retains configured bounded transport retries, all sharing the pipeline deadline. Errors propagate as existing provider/retrieval exceptions or `AssessmentValidationError`; failed output is never returned as a normal assessment. F06 adds the complete public failure envelope, broader validation and bounded synthesis repair.

`SYNTHESIS_MAX_COMPLETION_TOKENS` defaults to 4096 and is capped by `PROVIDER_MAX_COMPLETION_TOKENS`. Synthesis requests temperature zero. The normal configured deadline remains 90 seconds. Metadata records requested and returned model identities, prompt/schema hashes (including the actual request-bound synthesis schema), corpus/retrieval versions, stage timings and token usage reported for each stage's last successful provider call. Reported usage is not a measured aggregate across transport attempts or extraction repair calls.

## Live development checks

```powershell
.\.venv\Scripts\python.exe -m backend.smoke_assessment --provider llmtech --public-trial
```

The diagnostic runner defaults to D01 and D02 from the development enquiry fixture, runs every stage freshly, and saves timestamped records under `outputs/assessment/`. Routine timestamped runs are ignored by Git; source-reviewed records are retained through explicit `.gitignore` exceptions alongside their review receipts. Use repeatable `--case D01` or `--case D02` to select cases. Its run-only defaults are a 180-second pipeline deadline and a 60-second provider-call timeout; `--request-deadline-s` and `--call-timeout-s` can change these within existing settings bounds.

The LLMTech override uses `nvidia/Qwen3.8-27B-NVFP4`. The explicit public-trial flag retrieves the documented trial only if no backend LLMTech key is configured. Saved provider settings are unchanged. Corpus evidence is sent to the selected provider for synthesis; credentials remain backend-only. Failures retain successfully completed stage outputs and sanitized diagnostics separately from successful assessments.

The inspection receipt at `outputs/assessment/review.json` identifies reviewed outputs and distinguishes automated checks, live execution and agent source comparison. Agent review is not independent human or scientific validation. Earlier failed or superseded attempts remain available.
