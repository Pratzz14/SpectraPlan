# SpectraPlan Iterative Implementation Plan

**Based on:** [Technical specification v1.1](spec.md)\
**Status:** F01–F07 implemented for their recorded development gates; start F08 development evaluation next\
**Reconciled:** 2026-10-18, against implementation through commit `844a835`\
**Structure:** Main feature → tasks → subtasks\
**Target:** A working, source-grounded spectroscopy assessment app with reproducible evaluation outputs.

## How to use this plan

Work through the main features in order. Each task has a stable ID so you can request a small increment, such as “Implement F02.2,” or a complete feature, such as “Implement F04 and verify its completion gate.” Check off a subtask only after its work is complete; check off a parent task only when all its subtasks are complete.

At the end of each iteration, record the files changed, checks performed, remaining issues and next task in the progress log. Keep a feature unfinished if its completion gate has not passed. Distinguish source inspection, automated tests, live model calls and browser verification; one does not establish the others.

The specification remains the authority for scientific requirements and evidence boundaries. The current-baseline section below records implemented project choices that extend its original UI, provider and optional-feature scope. Checkmarks reflect recorded implementation evidence; unresolved evaluation and provider-specific live checks remain open.

## Current baseline and changes from the initial plan

Resume at **F08.1**. F01–F07 do not need to be implemented again. Their completion means the recorded application gates passed, not that all development cases or scientific claims have been evaluated. F08–F10 remain unfinished.

| Area | Implemented baseline to preserve | Consequence for the remaining plan |
|---|---|---|
| Technical knowledge | Versioned PDF/workbook evidence, automated eligibility checks, optional human verification, local BGE/Qdrant + BM25 hybrid retrieval | Evaluate the published corpus first; rebuild only for a demonstrated evidence/ingestion defect. No mandatory expert-approval step |
| Business context and inspection | Separate S06 website snapshot, manual search comparison and Extracted knowledge workspace | Website/vendor claims remain excluded from default technical assessment evidence; inspection is not scientific validation |
| Providers | `auto` defaults to Gemini → LLMTech Qwen → Groq Qwen; pinned modes remain available. Availability checks, bounded repair/fallback and actual stage identities are recorded | Freeze the provider policy and effective settings for evaluation; record actual models per stage rather than assuming every run used Gemini |
| Assessment API | `POST /api/assess` wraps extraction → retrieval → synthesis with complete/incomplete envelopes and a shared deadline | The evaluation runner should exercise this route, including request composition and durable history, rather than recreating its orchestration |
| Clarifications | Separate `clarification_answers`, linked questions and successive enquiry rounds; original enquiry editing remains supported | Evaluate initial answers separately from clarification rounds, preserving original text, effective input and answer provenance |
| Persistent history | Local SQLite enquiries, immutable rounds and chronological retrieval/model/validation traces; separate History page with reopen/continue | Use a dedicated evaluation database and export needed traces explicitly; the ignored local database is not the submission artifact |
| Interface and export | Assessment / History / Search sources / Extracted knowledge / Workspace navigation; embedded evidence drawer, JSON, report copy, chemist PDF and trace PDF | Extend regression coverage to history, clarification and both PDF audiences; compare each export with its selected run |
| Gemini source comparison | Separate original-file extraction comparison with source hashes and location checks | Comparison artifacts do not publish a new corpus. Gemini-specific success remains a separate live check |

**Recorded verification and limits:** F06/F07 receipts below establish API and browser workflows. The later [Gemini/history receipt](../../outputs/provider_smoke/gemini_history_review.json) records 289 backend tests, 17 frontend tests, a production build, controlled browser checks and live D01/D02 assessments through Qwen fallback. Those are historical results at the receipt's recorded hashes, not a fresh test of every subsequent change. The receipt reports Gemini daily-quota failures and a staged source pilot; it does not establish successful live Gemini generation or a new full corpus build. The active pointer inspected for this reconciliation remains `corpus-4aac882441587796afe5`.

**F08 entry gaps:** D01–D08 are now stored verbatim with source paragraph locations and the supplied DOCX hash; `evaluation/run_evaluation.py` now runs them through the public API with isolated history and incremental manifests. `evaluation/final.json` and the original H01–H06 material remain an F09 dependency. The F07 live review's NIR/MIR source-relevance finding has been reproduced as a general method-rationale conflict check and corrected in the synthesis validation/prompt; fresh provider outputs must still receive semantic source review.

Existing diagnostic runners and receipts are useful starting points, but they do not complete the eight-case development review or the six-case final evaluation. Keep Gemini quota/comparison limitations explicit; an evaluation using an available, recorded Qwen provider need not wait for a Gemini corpus rebuild.

## Implementation sequence

The timeboxes retain the specification's original proposed 12-hour budget for reference. They are not actual elapsed time or fresh estimates: provider routing, persistent history and PDF exports expanded the implemented scope. Re-estimate F08–F10 from the remaining gates below. If a gate takes longer, reduce optional scope rather than marking unfinished work complete.

| Order | Main feature | Depends on | Target time | Observable result |
|---|---|---|---:|---|
| F01 | Project foundation and provider connection | None | 0.5 h | Backend, frontend and model smoke test run |
| F02 | Reviewed AFS knowledge base | F01 | 1.5 h | Inspectable passages and method rows with provenance |
| F03 | Customer enquiry extraction | F01 | 1.25 h | Facts, unknowns and separate contexts from an enquiry |
| F04 | Evidence retrieval | F02, F03 | 1 h | Relevant evidence ledger for each enquiry |
| F05 | Structured technical assessment | F04 | 1.25 h | First provisional assessment from the real pipeline |
| F06 | Feasibility planning and validated API | F05 | 1.5 h | Complete API result with checks and bounded failures |
| F07 | Assessment interface, history and export | F06 | 2 h | Browser enquiry → clarification rounds → evidence → JSON/PDF |
| F08 | Development evaluation and fixes — next | F07 | 1.5 h | Reviewed D01–D08 results, source-relevance fixes and current-workflow regressions |
| F09 | Reproducible final evaluation | F08 | 1 h | Six generated final outputs and manifest with actual provider identities |
| F10 | Reproducible setup and demonstration | F09 | 0.5 h | Fresh-start instructions, slides and demo |
| | **Total** | | **12 h** | |

**Current milestone:** F02–F07 support the complete application workflow. Next, evaluate the general pipeline and its claim support across all eight development cases, then freeze it for F09. Expand corpus coverage only where review demonstrates a gap.

## F01 — Project foundation and provider connection

**Outcome:** A minimal local application and a verified route to the selected model provider.\
**Spec:** Sections 4, 7 and 11.\
**Primary files:** `backend/main.py`, `frontend/`, `requirements.txt`, `.env.example`, `.gitignore`, `README.md`.

- [x] **F01.1 — Establish the project structure**
  - [x] Inspect the existing workspace and applicable instructions; preserve existing files and initialize Git if needed.
  - [x] Create the backend, frontend, knowledge, evaluation, outputs and tests directories described in the specification.
  - [x] Configure Python dependencies and a React/TypeScript/Vite/Tailwind application; record the actual dependency versions and startup commands.
  - [x] Ignore credentials, local environment files, dependency directories and temporary artifacts while keeping required evaluation outputs eligible for version control.

- [x] **F01.2 — Configure the backend and provider**
  - [x] Load provider endpoint, model, API key, source paths and timeout settings from backend configuration; supply placeholders in `.env.example`.
  - [x] Implement readiness reporting that distinguishes a running service from an unavailable corpus; never expose secrets.
  - [x] Add a provider adapter with bounded retries and locally validated structured responses.
  - [x] Run one small live structured-output smoke test and record the outcome; report a missing key or unavailable provider as an unresolved dependency.

- [x] **F01.3 — Connect the development environment**
  - [x] Start the backend and frontend locally and configure the development API connection.
  - [x] Confirm the frontend can display backend readiness without making a paid model call.
  - [x] Add initial setup/run instructions to the README as the commands become known.

**Completion gate:** Both services start, frontend-to-backend communication works, and the selected provider returns a locally validated response. Missing corpus readiness is expected until F02; a mocked provider alone does not complete the live-provider gate.

**Observed F01 status (2026-10-17): Complete.** Local services, readiness API, development proxy and browser checks pass. Selected provider: Groq `qwen/qwen3.8-27b`, with configurable medium reasoning and strict JSON Schema plus local Pydantic validation. After the key was supplied locally, the [successful live smoke record](../../outputs/provider_smoke/20261017T094530Z_0cb5a2339fbc465d895e14d32f6745ea.json) captured `sample_phase="powder"` and `target="moisture"`, with local schema/content validation and exit 0. The [earlier missing-key attempt](../../outputs/provider_smoke/20261017T092630Z_d3e51022e47a4ec4ab8a9cfb114b34f3.json) is preserved. The corpus was missing at this earlier milestone; F02 is now published as recorded below. F03 onward remain future work.

## F02 — Source-grounded AFS knowledge base

**Outcome:** Reproducible technical evidence with source locations, automated validation and optional manual verification. No mandatory approval workflow.\
**Spec:** Section 5 and `docs/knowledge_pipeline.md`.\
**Primary files:** `backend/ingest.py`, `knowledge/source_manifest.json`, `knowledge/passages.jsonl`, `knowledge/methods.json`.

- [x] **F02.1 — Inventory and separate materials**
  - [x] Map S01–S06 and T01 to exact filenames; compute hashes, PDF page counts and workbook dimensions.
  - [x] Exclude development, evaluation, challenge and unknown content from technical retrieval.
  - [x] Classify S05/S06 as business context and use configurable source locations.
- [x] **F02.2 — Implement page-level extraction and source checks**
  - [x] Extract exact source blocks, render pages, retain 1-based page locations and quotation offsets.
  - [x] Add versioned Qwen extraction/verification prompts with strict schemas and separate figure transcriptions.
  - [x] Separate automated validation, human verification and technical retrieval eligibility.
  - [x] Complete the live 64-page corpus build and inspect representative text and high-value S02 figures.
- [x] **F02.3 — Import the method table**
  - [x] Preserve all 19 rows, nine columns and seven notes, with workbook sheet/row and S01 Table 1 p.6 provenance.
  - [x] Preserve qualitative ratings, optical depth/path and fiber-length distinctions.
- [x] **F02.4 — Verify end-to-end ingestion**
  - [x] Test locations, stable IDs, caching, method rows, exclusions, report escaping and atomic publication.
  - [x] Implement local BGE embeddings, token checks, Qdrant, BM25 and RRF search.
  - [x] Document rebuild commands and manual inspection without an approval step.
  - [x] Verify full live corpus, unchanged-source rebuild and representative real hybrid searches.

**Completion gate:** Every active record resolves to its source and passes defined automated checks; all workbook data and notes survive; ambiguous and excluded records are inspectable; and the published corpus/index revisions agree. Human verification is optional and never implies AFS approval. Keep the live gate open until it is evidenced.

**Observed F02 status (2026-10-17): Complete.** The LLMTech ingestion override resumed the saved checkpoint, retried S04 p.5 verification, processed all 64 pages, imported 19 method rows and seven notes, built local BGE/Qdrant/BM25 indexes, and atomically published `corpus-4aac882441587796afe5`. Validation passed with 152 passages, 81 eligible passages, 19 eligible methods, 63 flagged records and zero human-verified records. Representative powder/API and opaque-dairy searches returned records from both BM25 and Qdrant. An unchanged cached rebuild preserved the corpus version and evidence IDs/revisions. The embedded Qdrant store must not be queried concurrently because its local file lock is single-client. The evaluation scenario file remains intentionally excluded from F02 and is an F09 input.

## F03 — Customer enquiry extraction

**Outcome:** Typed customer facts with unknowns and multiple process streams preserved.\
**Spec:** Sections 6.1 and 9.2.\
**Primary files:** `backend/models.py`, `backend/agent.py`, `tests/`.

- [x] **F03.1 — Define fact and provenance models**
  - [x] Implement `CaseFacts`, `MeasurementContext`, `CustomerStatement` and fact-provenance records with safe collection defaults.
  - [x] Represent reported facts, requested outcomes, proposed approaches and customer claims separately.
  - [x] Preserve exact supporting input quotes, context IDs, raw ranges and units; use `null` for unknown values.

- [x] **F03.2 — Implement structured extraction**
  - [x] Write a versioned extraction prompt that records only what the customer states and does not recommend a method.
  - [x] Separate distinct streams/targets into contexts and preserve shared constraints without inventing per-stream facts.
  - [x] Parse and validate extraction output; reject malformed structures and untraceable input quotes.
  - [x] Expose extraction through a callable pipeline stage; add `/api/extract` only if useful for development.

- [x] **F03.3 — Check extraction behavior**
  - [x] Verify D01/D02 produce the stated sample properties, targets and unknowns.
  - [x] Test a synthetic multi-stream enquiry and a customer assertion of an unproven instrument capability.
  - [x] Test missing numerical values and ambiguous units; confirm they do not become assumed defaults or unsupported conversions.

**Completion gate:** Extracted facts trace to the enquiry, separate streams remain separate, and customer requests cannot silently become verified technical capabilities.

**Observed F03 status (2026-10-17): Complete for the tested development cases.** Implemented typed models, a versioned quoted-value extraction schema, deterministic provenance construction, exact quotation/value checks, separate context/shared-constraint validation, raw quantity preservation and one bounded repair. `POST /api/extract` uses the same corpus-independent stage. The full backend suite passed **122 tests**. Final `extraction-v6` outputs for D01/D02 and the three synthetic cases passed mechanical checks and agent comparison against their enquiry text using user-authorized LLMTech `nvidia/Qwen3.8-27B-NVFP4`. [Review and exact run records](../../outputs/extraction/review.json) distinguish this inspection from independent human/scientific validation. Earlier Groq request-size/HTTP 429 failures and earlier extraction defects are preserved. Saved interactive provider settings were not changed; see [provider setup](../customer_extraction.md). F04 remains separate future work.

## F04 — Evidence retrieval

**Outcome:** A bounded, inspectable evidence set that supports the assessment.\
**Spec:** Sections 5 and 9.1.\
**Primary files:** `backend/retrieval.py`, `tests/`.

- [x] **F04.1 — Implement lexical search**
  - [x] Build BM25 over reviewed technical passages and expose a deterministic search function.
  - [x] Form queries from each context's target, matrix, process, requested method and consequential unknowns.
  - [x] Add a small documented domain synonym map where needed; exclude scenario IDs and scenario-specific phrase matching.

- [x] **F04.2 — Combine passages and method rows**
  - [x] Retrieve relevant method-table rows alongside passages and place both in one evidence ledger.
  - [x] Deduplicate and balance support across contexts, geometry, compatibility and limitations where relevant.
  - [x] Target four to eight meaningful records, with eight as the total cap; never pad weak results.
  - [x] Permit one additional targeted/broadened search and expose any remaining evidence gap.

- [x] **F04.3 — Implement evidence resolution**
  - [x] Resolve evidence IDs to the exact source revision, file, page, reviewed text/transcription and optional workbook locator.
  - [x] Implement `/api/evidence/{evidence_id}` using the allowlisted corpus rather than arbitrary file paths.
  - [x] Test relevant retrieval on development enquiries, missing support, unknown IDs and unreviewed records.

**Completion gate:** A developer can inspect why each returned record is relevant. A successful empty search is distinguishable from a broken index, and table evidence has the same traceability as PDF evidence.

**Observed F04 status (2026-10-17): Complete for the inspected development cases.** Context-aware BM25/local BGE/Qdrant retrieval and structured method lookup produce a version-pinned ledger of at most eight records, with scores, selection reasons, context/facet associations, one follow-up query and explicit gaps. Added `POST /api/retrieve` and `GET /api/evidence/{evidence_id}` with exact record/corpus revisions and workbook notes. The full backend suite passed **145 tests**. Real-corpus HTTP checks resolved every D01 ledger record exactly; development diagnostics returned 5 records for D01, 4 for D02, 8 for the multi-stream case and zero for an unsupported target. The ambiguous-input case retains an application gap after its follow-up. [Inspection receipt](../../outputs/retrieval/review.json) records source-relevance findings and heuristic/scientific limits. See [retrieval contract](../evidence_retrieval.md). No provider calls, source rebuilds, frontend changes or assessment generation were added.

## F05 — Structured technical assessment

**Outcome:** A real first assessment with conditional method choices, questions and source-backed reasoning.\
**Spec:** Sections 6.2, 9.3 and 5.1.\
**Primary files:** `backend/models.py`, `backend/agent.py`.

- [x] **F05.1 — Define the assessment contract**
  - [x] Implement requirements, prioritized questions, recommendations, spectral ranges, assumptions, risks and experiment fields from the specification.
  - [x] Define scientific decision statuses and their required reasons; allow an empty shortlist for justified insufficient-information/outside-scope outcomes.
  - [x] Model technical assertions with `text` and `evidence_ids`; preserve context references throughout the assessment.

- [x] **F05.2 — Implement evidence-grounded synthesis**
  - [x] Supply extracted facts and the retrieved evidence ledger to a versioned synthesis prompt.
  - [x] Generate a concise conditional shortlist, useful clarification questions and high-level measurement concepts.
  - [x] Distinguish nominal spectral range from usable equipment coverage, and Raman excitation from Raman shift.
  - [x] Keep customer assumptions, source limitations and contradictory evidence visible; treat document text as data rather than executable instructions.

- [x] **F05.3 — Build the first working backend flow**
  - [x] Connect extraction → retrieval → synthesis through one reusable assessment pipeline.
  - [x] Run D01 and D02 through that pipeline with the real provider and reviewed corpus.
  - [x] Inspect the resulting method choices, questions and citations against the source material; correct general prompt/retrieval issues.

**Completion gate:** The pipeline produces a typed provisional result with source-supported reasoning for a development enquiry. Treat it as a development result until F06 validation and failure handling are complete.

**Observed F05 status (2026-10-17): Complete for the inspected development gate.** Implemented strict assessment models, conditional scientific statuses, source-excerpt assertions, explicit unknown spectral coverage and separate Raman excitation/shift quantities. The reusable Python pipeline runs fresh extraction → pinned retrieval → synthesis with one shared deadline. Python constructs customer requirements, source indexes and conservative individual-method comparison/reference-alignment proposals. The full backend suite passed **191 tests**. Final `extraction-v7` / `synthesis-v8` live LLMTech runs produced provisional D01 (NIR and Raman) and D02 (NIR reflection) results. [Source-comparison receipt and exact artifacts](../../outputs/assessment/review.json) record source checks, prompt/schema hashes, earlier failures and residual semantic/editorial limitations. This is agent source inspection, not independent scientific validation; full validation/repair, feasibility completion and the public assessment API remain F06 work. See [technical assessment](../technical_assessment.md).

## F06 — Feasibility planning and validated API

**Outcome:** A complete assessment API with a practical first experiment and explicit failure behavior.\
**Spec:** Sections 6.3, 7 and 9.3–9.4.\
**Primary files:** `backend/agent.py`, `backend/validation.py`, `backend/main.py`, `backend/models.py`, `tests/`.

- [x] **F06.1 — Complete feasibility-study output**
  - [x] Generate objective, representative samples/process states, independent reference measurements and relevant variation to cover.
  - [x] Compare suitable individual methods before combinations, aligning sample location and timing where needed.
  - [x] Propose independent validation at the batch/run/specimen/patient level appropriate to the task; avoid treating repeated scans as independent samples.
  - [x] Tie go/no-go criteria to customer requirements, leave missing thresholds open, and label proposed experimental settings as proposals.
  - [x] For an undefined target, propose initial characterization and clarification before analyte calibration or an exact configuration.

- [x] **F06.2 — Implement mechanical validation and bounded repair**
  - [x] Validate schemas, context IDs, input-quote provenance and every evidence reference against the retrieved reviewed ledger.
  - [x] Check provenance for structured quantities and explicit configured conflicts; do not claim these checks prove arbitrary scientific prose.
  - [x] Permit one content repair per provider using specific errors and the same evidence set within the total request deadline; automatic routing can then try the next configured provider under the same validation rules.
  - [x] Construct the final source index and run metadata on the backend; include all cited evidence records in the exportable envelope.

- [x] **F06.3 — Expose the assessment contract**
  - [x] Implement `POST /api/assess` with blank/oversized input validation and the default 8,000-character limit.
  - [x] Return the run envelope with validated facts, assessment, errors, model identity and prompt/corpus/pipeline versions.
  - [x] Separate `run_status` from scientific `decision_status`; incomplete results have `assessment=null` and a failed-stage error.
  - [x] Implement the specified HTTP error mapping, per-call limits and shared deadline across retries, search and repair.

- [x] **F06.4 — Verify successful and failing runs**
  - [x] Exercise valid D01/D02 assessments and a justified empty-shortlist assessment. D01/D02 and undefined-target empty-shortlist characterization passed live through the API with LLMTech, alongside local API tests.
  - [x] Test nonexistent evidence, missing provenance, invalid model JSON, exhausted repair, provider timeout and unavailable corpus.
  - [x] Verify an evidence gap can yield a complete cautious assessment while infrastructure failures remain incomplete/error states.

- [x] **F06.5 — Integrate shared provider routing and explainability**
  - [x] Support Gemini-first automatic selection, LLMTech/Groq fallbacks and pinned providers with cached availability and bounded attempts within the shared deadline.
  - [x] Record actual stage providers/models, sanitized attempt metadata and chronological extraction/retrieval/synthesis events.
  - [x] Create durable enquiry rounds before model work; preserve original/revised descriptions, linked clarification answers, effective input, questions and stored results.

These additions are implemented; Gemini-specific live generation and original-file comparison success remain separately unresolved in the later receipt. Trace capture and fallback success do not establish scientific claim support.

**Completion gate:** The API returns a validated, inspectable complete result or the documented incomplete/error contract. Failed synthesis cannot appear as a normal technical recommendation.

**Observed F06 status (2026-10-18): Complete for the inspected development gate.** The backend suite passed **236 tests**. Fresh LLMTech D01/D02 API runs returned complete provisional assessments at the default 90-second request / 30-second call limits, in about 26/23 seconds. Agent source comparison checked cited passages/rows, workbook scope, original source hashes and practical study design. An initial customer-summary source leak was corrected with backend-rendered facts, tested and rerun. [Live envelopes](../../outputs/assessment/20261018T031435Z_573cc337a2c7459cb0d31246fe0eebfe.json), [mocked empty/failure envelopes](../../outputs/assessment/f06_mocked_api.json) and the [verification receipt](../../outputs/assessment/f06_review.json) preserve exact evidence, hashes, earlier findings and residual semantic/editorial limits. A separately approved [live undefined-target check](../../outputs/assessment/f06_live_gap.json) returned a complete insufficient-information result with an empty shortlist in about 8 seconds, without repair. Agent inspection is not independent scientific validation.

## F07 — Assessment interface, history and export

**Outcome:** Responsive workspaces for entering enquiries, continuing saved rounds, reviewing evidence and exporting actual results.\
**Spec:** Sections 3 and 8.\
**Primary files:** `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/assessment.ts`, `frontend/src/components/`, `backend/explainability.py`, `backend/history_pdf.py`.

- [x] **F07.1 — Build the enquiry and request flow**
  - [x] Add a labeled enquiry textarea, Analyze action and blank-input prevention.
  - [x] Define matching TypeScript contracts and connect to `/api/assess`.
  - [x] Implement empty, loading, success, incomplete and error views with useful stage/error text.
  - [x] Prevent stale requests from replacing newer results and disable stale copy/download actions during reassessment.

- [x] **F07.2 — Render the assessment**
  - [x] Build requirements, clarification, recommendation and experiment components.
  - [x] Separate facts, unknowns and assumptions, grouping stream-specific content by context.
  - [x] Display decision reason, conditional status, geometry, qualified range and limitations without fabricated confidence percentages.
  - [x] Render empty-shortlist and research-only/outside-scope assessments with their useful questions and next steps.

- [x] **F07.3 — Add evidence inspection and export**
  - [x] Make claim-level citation controls open an evidence drawer with source location, scope and reviewed content.
  - [x] Label figure transcriptions and workbook-derived evidence accurately.
  - [x] Download the actual run envelope with resolved evidence and metadata; copy report text derived from the same result.
  - [x] Support editing the original enquiry and submitting it again as the required clarification workflow.

- [x] **F07.4 — Verify the browser workflow**
  - [x] Run a live enquiry from input through result, evidence inspection and JSON download.
  - [x] Inspect desktop and narrow layouts, keyboard access, readable result sections and visible errors.
  - [x] Confirm the downloaded envelope matches the displayed run; exercise resubmission, empty shortlist and a failed request.

- [x] **F07.5 — Add clarification rounds, saved history and PDF reports**
  - [x] Submit separate clarification answers linked to issued questions and retain enquiry/parent-run/round identity across reassessment.
  - [x] Provide a History workspace to list enquiries, select rounds, inspect/export traces and continue a saved enquiry without replacing the active draft merely by viewing history.
  - [x] Export a chemist-facing assessment PDF and a separate trace PDF from the selected stored run through `/api/assess/{run_id}/report.pdf` with `audience=chemist` or `audience=trace`.
  - [x] Retain shared search/knowledge/status workspaces and same-run JSON/report copy with stale-result protection.

**Completion gate:** A user can complete the entire browser workflow, inspect support for a claim and export the same run. Record browser evidence separately from backend-only tests.

**Observed F07 status (2026-10-18): Complete for the browser workflow gate.** The assessment page is the default view; `#search` and `#status` retain the diagnostic tools. The browser submitted an unedited D01 enquiry to the real local API with LLMTech (`nvidia/Qwen3.8-27B-NVFP4`), returning complete provisional run `69ae3c206b3e4c4bb1ad7d77c5207b8e`. Citation inspection used the run's embedded evidence, report copy used the same result, and the downloaded JSON deep-equaled the entire captured API envelope. Microsoft Edge via Playwright was used because the Browser plugin was unavailable. Desktop 1440×1000 and narrow 390×844 checks covered layout, keyboard citation access, modal focus containment/restoration, Escape, exact evidence content and navigation without relevant console errors or horizontal overflow. An initial dialog Tab-focus defect was fixed and the live flow rerun successfully.

**Controlled browser evidence is separate from live execution:** route fixtures cover workbook notes, figure-transcription/research labels, qualified spectral quantities, multiple streams, insufficient-information and outside-scope decisions, incomplete results, 422/500/503 and network failures, malformed responses, dangling citations, superseded requests, keyboard submission and clipboard recovery. These checks establish UI behavior, not scientific claim support. Browser scripts, successful receipts, screenshots, the exact live envelope and download are outside Git under `C:\Users\prati\.codex\visualizations\2026\10\18\01a14d23-42ec-75a1-b40a-ed8c0351992c\` (`f07-live-review.json`, `f07-controlled-review.json`).

**Automated checks are separate from browser evidence:** `npm test` passes five frontend contract/report tests; `npm run build` passes TypeScript and production bundling. The backend regression suite passes **262 tests** using `python -m pytest -q --basetemp tmp/f07-regression-outside`; it ran outside the restricted sandbox because async/socket operations stalled inside it. No backend implementation or API contract changes were required for F07. Scientific performance and source-claim entailment were not evaluated by this frontend gate. The live UI review did expose a backend source-relevance issue: the NIR rationale in the saved run cites a MIR-ATR/fluorescence passage on S01 p.14. The frontend displays the original response and support faithfully; recommendation/source entailment requires a separate backend follow-up and is not established by the F07 completion gate.

**F07 UI refinement after brief review (2026-10-18):** Compared the interface with the supplied challenge PDF, especially main process requirements/constraints on p.1 and structured requirements/questions/recommendation/risks/feasibility output on p.2. Retained a compact process summary to confirm interpretation, replaced schema-like field rows with readable grouped labels, and moved full extraction, attributed claims and original quotes into one keyboard-accessible review disclosure. Missing information remains available separately from stated facts. Removed the exact uncited generic clarification fallback from question rendering and copied reports; specific explanations, affected decisions and cited explanations remain. JSON exports preserve the entire original envelope. Seven frontend tests and the production build pass; Edge/Playwright checks at 1440×1000, 598×668, 675×668 and 390×844 verify disclosures, question/citation access, partial results and lossless export without uncaught runtime errors or horizontal overflow. These refinement checks use controlled responses with no new provider calls. The source-relevance limitation above remains a backend follow-up. Browser evidence is outside Git in the same visualization directory (`f07-refinement-review.json`, `f07-refined-*.png`).

**Compact workspace redesign (2026-10-18):** Implemented the three approved concepts with shared Assessment / Search sources / Extracted knowledge / Workspace navigation and no large title/status banners. Assessment supports direct clarification answers, original-enquiry editing, retained previous answers, collapsible results and exact same-run exports. Search retains BM25/Qdrant/hybrid comparison and website business-context boundaries. Extracted knowledge uses a read-only `/api/knowledge/inspection` endpoint sharing the legacy report data, with original source images, corpus-pinned artifact paths, review labels, workbook notes and excluded records. Twelve frontend tests, the production build and 265 backend tests pass. The first backend run had two timing/file-lock failures; both passed individually and the full fresh-directory run passed. Edge/Playwright at 1536×1024 and 390×844 verified controlled assessment failures, real search and published knowledge, source access, keyboard behavior and exports. Two fresh live provider runs completed the enquiry → direct clarification → reassessment → evidence → matching JSON workflow. Browser evidence and the concept comparison record remain outside Git in the visualization directory (`compact-workbench-review.json`, `compact-live-clarification.json`, `compact-*.png`). Scientific performance and claim-source entailment remain outside this UI verification.

## F08 — Development evaluation and fixes

**Outcome:** General pipeline problems are found and corrected before final evaluation.\
**Spec:** Section 10 and the acceptance checklist in section 14.\
**Primary files:** `evaluation/development.json`, `evaluation/run_evaluation.py` (new), `tests/`, `frontend/tests/`, `outputs/development/`; general fixes in `backend/agent.py`, `backend/retrieval.py`, `backend/validation.py` and affected UI modules only as justified by findings.

**Starting point:** Keep F01–F07 and the published corpus as the baseline. Reuse `backend/smoke_assessment.py`'s input/hash/output handling and in-process ASGI route invocation where useful. Its current defaults cover D01/D02 with 180-second request / 60-second call limits; a general evaluation runner still needs all eight inputs, a manifest and explicit production-equivalent limits. Use 90 seconds total / 30 seconds per call unless a different evaluation profile is deliberately recorded.

- [ ] **F08.1 — Prepare a generic development runner**
  - [x] Complete D01–D08 inputs from the supplied original, preserving exact enquiry wording, source hash and source locations; keep organizer worked answers available only for review.
  - [x] Implement reusable batch handling through the same `POST /api/assess` route used by the UI, saving exact returned envelopes, HTTP/run/scientific outcomes and failed attempts in timestamped directories.
  - [x] Keep case IDs in runner bookkeeping, not model input or runtime branching.
  - [x] Use a dedicated `EXPLAINABILITY_DB_PATH` for each evaluation run; retain enquiry/run IDs and export traces needed for review without mixing evaluation with personal saved history.
  - [x] Write a development manifest with exact submitted text or verifiable UTF-8 hashes, implementation revision, prompt/schema/configuration/corpus identity, effective limits, requested provider policy, actual stage providers/models, timings, output paths and hashes.
  - [ ] Separate initial assessments using unmodified source enquiries from optional clarification-round checks; save the actual answers and effective input for those follow-ups.

- [ ] **F08.2 — Review development results**
  - [ ] Compare D01/D02 with organizer worked examples for structure, caution and experiment quality without requiring identical wording or method rankings.
  - [ ] Run and inspect D03–D08 for coverage, matrix/geometry handling, target/proxy distinctions and research scope.
  - [ ] Check important claims against cited passages and log unsupported claims, critical missing questions and feasibility-plan weaknesses.
  - [ ] Reproduce and resolve the recorded NIR rationale / S01 p.14 source mismatch with a general retrieval/synthesis/validation improvement; add a meaningful regression and inspect fresh generated claims against their cited method, geometry, matrix and scope.
  - [ ] Fix general retrieval, schema or prompt issues and rerun affected cases. If the shared pipeline, provider policy or corpus changes, finish with one coherent D01–D08 run under the candidate F09 configuration; preserve earlier results.
  - [ ] Save a review log per case with run/decision status, source IDs and pages/rows, claim-support findings and severity, missing questions, experiment/independent-validation quality, reviewer identity/type and residual limitations. Record unchecked claim support as unreviewed, never zero unsupported claims by default.

- [ ] **F08.3 — Complete regression and failure checks**
  - [ ] Test a novel enquiry plus generic multi-stream, unspecified-target and unsupported-premise inputs.
  - [ ] Confirm input text and retrieved documents cannot override workflow rules or introduce arbitrary tools/URLs.
  - [ ] Verify missing/corrupt corpus, invalid output, exhausted per-provider repair, provider unavailability/quota/timeout and fallback with mocked failures; verify a live available provider separately. Check shared deadlines and actual per-stage identities, including mixed-provider runs.
  - [ ] Cover clarification question/answer ownership, parent-round conflicts, reload/reopen/continue, new-enquiry isolation, interrupted rounds and unavailable history storage; failures must not become scientific recommendations or overwrite earlier rounds.
  - [ ] Run relevant backend and frontend checks and the production build. Repeat desktop/narrow browser enquiry → clarification → reassessment → evidence → JSON/chemist PDF and History → selected round → trace JSON/PDF checks after material changes; verify selected-run identity, factual/citation fidelity, incomplete labels and stale-request protection. Render representative PDFs to inspect pagination, long content and readability.
  - [ ] Record human review, stubbed tests, live provider results and browser verification separately; unresolved material issues remain open.
  - [ ] Record the outstanding Gemini quota/comparison check separately. Retry Gemini-specific diagnostics when available if needed for the chosen evaluation policy; neither a failed comparison nor an unpublished pilot replaces the active corpus. Rebuild only for an identified defect, validate before publication and rerun affected cases afterward.

**Completion gate:** All eight initial development cases have machine-produced outcomes and source-support reviews under the recorded candidate configuration. Critical fabricated/misattributed claims discovered in review, including the recorded NIR citation mismatch, are resolved and rerun; uncertainty and runtime failures remain distinct. Current clarification/history/export behavior passes relevant regressions, and remaining provider-specific limitations are disclosed. Schema success alone is not a zero-unsupported-claims result. Hand off the runner, development manifest/review log, fixes and candidate settings to F09; final scenarios are not tuning inputs.

**F08 implementation checkpoint (2026-10-18):** The runner now validates the supplied DOCX hash and exact D01–D08 paragraphs, invokes the public assessment route with an isolated explainability database, records per-case envelopes/traces/PDFs and actual provider identities, and emits a review receipt that keeps semantic source entailment explicitly `unreviewed`. The general `method_rationale_mismatch` validation guard reproduces and blocks the earlier NIR rationale / MIR-ATR-fluorescence citation failure. The backend suite passes **298 tests**, the frontend suite passes **17 tests**, and the production build passes. A fresh automatic batch `outputs/development/20261018T104630Z_13bffba3ae73447982827b5f96da41d9/` completed D01–D07; D08 returned a recorded `provider_unavailable` synthesis result. A separate prior D08 retry completed with method-matched MIR/FTIR and fluorescence rationales, but this does not constitute one coherent all-eight batch. Clarification-round checks, semantic source review, fresh browser/export reruns and the Gemini-specific comparison remain open; no F08 completion claim is made.

## F09 — Reproducible final evaluation

**Outcome:** Six unedited application-generated final answers with traceable configuration.\
**Spec:** Sections 2 and 10.1.\
**Primary files:** `evaluation/final.json`, `evaluation/run_evaluation.py`, `outputs/H01.json`–`outputs/H06.json`, `outputs/run_manifest.json`, `outputs/runs/`.

- [ ] **F09.1 — Freeze the general pipeline**
  - [ ] Preserve the exact H01–H06 enquiry text from the supplied file and verify the stored inputs against it.
  - [ ] Record implementation revision, prompt/schema hashes and versions, corpus/index identity, effective time/token/repair/retrieval settings and provider policy. Either pin a verified provider/model or freeze automatic order and profiles, recording actual models/attempts per stage; one configuration does not imply one actual provider.
  - [ ] Verify original final-scenario material is available before generating `evaluation/final.json`; never reconstruct missing H inputs from memory or development cases.
  - [ ] Inspect runtime prompts, retrieval data, synonym maps and code for evaluation-case text, IDs or answer lookups; remove any case-specific behavior.

- [ ] **F09.2 — Generate and record all six outputs**
  - [ ] Run every unmodified final enquiry through the same assessment route as the UI with the F08 runner, isolated history storage and no added clarification answers; use IDs only to associate inputs with output filenames.
  - [ ] Save each full machine-produced envelope without manual answer editing.
  - [ ] Write a manifest containing input text or verifiable hashes, timestamps, frozen configuration identity, actual stage provider/model identities, enquiry/run IDs, output paths/hashes and HTTP/run/scientific outcomes; export any supporting traces needed without requiring the local SQLite database.
  - [ ] Confirm all six runs are complete; an incomplete/error record does not meet the submission requirement.

- [ ] **F09.3 — Verify the submission set**
  - [ ] Check each output's schema, evidence references and consistency with its manifest entry.
  - [ ] Preserve earlier and failed runs; if a general bug requires a change, version it and rerun all six under one configuration.
  - [ ] Describe these as organizer-provided evaluation scenarios, not an unseen benchmark, and record observed limitations.

**Completion gate:** H01–H06 each have a completed, unedited generated envelope under one recorded configuration, with their supporting evidence and manifest available in the repository.

## F10 — Reproducible setup and demonstration

**Outcome:** An evaluator can install the app, understand the architecture and see a short working demonstration.\
**Spec:** Sections 11, 13 and 14.\
**Primary files:** `README.md`, `.env.example`, presentation/demo materials, this plan's progress log.

- [ ] **F10.1 — Finish setup and architecture documentation**
  - [ ] Document installation, source placement, corpus rebuild, automatic/pinned provider configuration, startup, checks and the implemented development/final evaluation commands.
  - [ ] Explain the pipeline, source handling, citation scope, uncertainty behavior and known limitations.
  - [ ] Document external sources if any, keep external retrieval disabled by default, and avoid publishing supplied originals unless redistribution is established.
  - [ ] Verify a fresh setup using the instructions and confirm that credentials are absent from tracked files and outputs.
  - [ ] Document local history storage, enquiry continuation, chemist versus trace exports and the fact that traces contain enquiry/source/model content. Reconcile the specification's earlier provider/API examples and deferred-feature list with the implemented scope and final evidence.

- [ ] **F10.2 — Prepare the five-minute demonstration**
  - [x] Create concise slides covering the customer problem, workflow, architecture, evaluation and limitations.
  - [ ] Rehearse a development/novel enquiry through facts, recommendations, evidence and feasibility plan, followed by a clarification round/history reopen and same-run export; include a contrasting uncertainty case within the time limit.
  - [x] Add a timed script with a clearly labelled prior-run fallback; live timing and environment verification remain open.

- [ ] **F10.3 — Close the implementation checklist**
  - [ ] Review every acceptance item in specification section 14 against actual evidence.
  - [ ] Record completed features, deferred optional items and remaining limitations in the progress log and README.
  - [ ] Confirm required code, reproducibility instructions, final outputs, manifest and presentation materials are present.

**Completion gate:** The documented fresh-start workflow works, required artifacts are present, and the demonstration makes claims supported by observed results.

## Optional work after the required workflow

These items do not block the MVP. Keep them deferred until the required completion gates pass.

- [ ] **O01 — Structured fact editing:** add context-aware user corrections, preserve correction provenance, reject unknown fields and rerun affected pipeline stages.
- [x] **O02 — Extraction endpoint:** `/api/extract` was implemented in F03.
- [ ] **O03 — Model-selected search:** consider only after evaluating deterministic retrieval; hybrid BM25/BGE/Qdrant retrieval and manual search comparison are already implemented.
- [ ] **O04 — Later product features:** expert approval/review workflow, verified hardware catalog and offline spectral-data analysis remain deferred. Local persistent enquiries, analysis-round history and PDF exports are already implemented; they do not establish expert approval.

Direct clarification answers and original-enquiry editing are already supported. O01 refers specifically to structured field overrides; non-null `fact_overrides` remain unsupported.

## Scope reduction when time is short

| Checkpoint | Action |
|---|---|
| Retrieval is not usable by hour 4 | Use a smaller manually reviewed, page-cited corpus; retain provenance and generic retrieval |
| Extra model tooling consumes time by hour 6 | Keep backend-directed retrieval and one structured synthesis stage |
| A complete assessment is unavailable by hour 7 | Finish F05/F06 before adding UI polish |
| UI remains unfinished by hour 9 | Use the minimal input, result sections, expandable evidence and JSON export |
| Hour 10.5 is reached | Freeze optional features and protect time for final outputs, setup and demo |

Do not reduce scope by removing citations, fabricating missing facts, manually editing final answers or treating failed runs as completed evaluations.

## Progress log

Add one row after each implementation increment. Include the exact check/command and its outcome where useful; use a file path or run ID for evidence that would make the table unwieldy.

Entries below are historical checkpoints. Their then-current next steps, provider choices and open gates are superseded by the current baseline and later completed milestones above.

| Date | Task IDs | Status | Files changed | Verification and outcome | Remaining issue / next task |
|---|---|---|---|---|---|
| 2026-10-17 | F01.1, F01.2 configuration/adapter, F01.3 | Local foundation verified; live gate open | Backend configuration/health/provider/smoke modules; frontend; pinned dependencies; `.env.example`; ignore rules; tests; README | `python -m pytest -q --basetemp=tmp/pytest-runtime`: 50 passed; `python -m pip check`: no broken requirements; `npm run build`: typecheck and Vite build passed; direct backend and Vite-proxied `/api/health`: HTTP 200, service running, ready false; ignore checks preserve required outputs | API key not supplied; F01.2 live response unresolved |
| 2026-10-17 | F01.3 browser verification | Passed | React readiness page and Vite proxy | Installed Chrome via bundled Playwright (Browser plugin unavailable), 1440×1000 and 390×844: correct page identity, meaningful content, no framework overlay or normal console errors, loading, real proxy refresh, keyboard refresh, no horizontal overflow, simulated HTTP 503 error and recovery through the real backend. Screenshots inspected outside the repository. | Assessment workflow and scientific validation belong to later features |
| 2026-10-17 | F01.2 live smoke attempt | Unresolved dependency | Timestamped record under `outputs/provider_smoke/` | `python -m backend.smoke_provider`: exit 1, `provider_not_configured`, no model call; run ID `d3e51022e47a4ec4ab8a9cfb114b34f3` | Supply backend-only `GROQ_API_KEY`, rerun, preserve this earlier record |
| 2026-10-17 | F01.2 live provider verification; overall F01 gate | Complete | New timestamped smoke record; README; checklist | `python -m backend.smoke_provider`: exit 0; real Groq `qwen/qwen3.8-27b` response passes strict local schema and synthetic-fact checks (`powder`, `moisture`); run ID `0cb5a2339fbc465d895e14d32f6745ea`. Earlier missing-key record retained. Backend restarted; real browser refresh confirms provider configured, corpus missing and ready false, with no console errors. `.env` remains ignored; smoke records contain no API key. | F02 reviewed knowledge base; missing corpus readiness remains expected |
| 2026-10-17 | F02.2, F02.4 | Complete | `backend/ingest.py`, `backend/retrieval.py`, published `knowledge/versions/corpus-4aac882441587796afe5`, `README.md`, this plan | `python -m backend.ingest build --provider llmtech --public-trial`: all 64 pages processed and publication passed; `python -m backend.ingest validate`: passed; representative powder/API and opaque-dairy searches returned both `bm25` and `qdrant` branches; `python -m backend.ingest report`: report rendered; unchanged cached rebuild preserved corpus version and evidence IDs/revisions; backend `pytest`: 69 passed; frontend `npm run build`: passed | F03 customer enquiry extraction is next. The missing final-evaluation scenario file is intentionally excluded from F02 and remains an F09 dependency |

**Runner note:** Python asynchronous networking and the Vite proxy stalled inside the restricted Windows sandbox. Tests and both servers were verified outside it; a minimal traceback located the stall in Windows `socketpair` during event-loop creation. Workspace-local temporary paths resolved the separate `ensurepip` write restriction. These accommodations do not change application behavior.

**Suggested next iteration request:** “Complete F08.2/F08.3: review the generated D01–D08 claims against their cited source passages, record the per-case review receipt, rerun any materially corrected cases as one coherent batch, and finish the clarification/history/export regression checks before freezing F09. Preserve prior results and keep final scenarios out of tuning.”


### 2026-10-17 — F02 implementation and bounded live validation

**Historical checkpoint, superseded by the completed F02 milestone above.** The failures and open gates below describe the earlier Groq pilot, not the current published corpus.

Implemented the ingestion CLI, strict Qwen text/visual extraction and separate verification contracts, exact source anchors, immutable generations with atomic publication, workbook import, the inspection report and local Qdrant/BM25 search. Updated readiness fields and frontend language to separate automated eligibility from optional human verification; no approval workflow is required. Added the pipeline contract and rebuild instructions.

Verification evidence:

- Automated backend tests and dependency checks pass; exact final test count is recorded in `outputs/ingest/test_validation.json`.
- Frontend TypeScript/production build passes. Playwright with installed Microsoft Edge verifies the real localhost readiness page at 1440×1000 and 390×844, status refresh, report filtering, all 19 method rows, seven notes, source images and empty search state. Browser plugin unavailable; bundled Chromium absent; installed Edge used. No relevant console errors after adding the report favicon. See `outputs/ingest/frontend_qa.json` and `report_qa.json`.
- Real local BGE embeddings, persistent Qdrant and BM25 run on synthetic evidence. Both retrieval branches participate; index checksums remain valid after search. This is component evidence, not real-source scientific validation.
- Inventory confirms all eight supplied files and 64 PDF pages. The live Qwen pilot extracts and separately verifies an eligible S01 p.10 passage. S02 p.6 fails provider strict JSON generation after the bounded retry (`HTTP 400`, `json_validate_failed`). No full corpus or partial pilot is published. See `outputs/ingest/live_validation.json`.
- API errors additionally report 7K input TPM and 1K output TPM within the account's displayed 8K TPM. Compact references, token pacing, separate stage caches and bounded JSON-generation retries are implemented. The original interactive provider setting remains unchanged.

Remaining gate: resolve the live visual extraction output-budget failure, complete all supplied-source page jobs, deeply validate/publish, repeat an unchanged cached rebuild and verify real D01/D02-related hybrid searches. `python -m backend.ingest build` resumes compatible caches. F02 is not marked complete.

### 2026-10-17 — LLMTech extraction checkpoint

**Historical checkpoint, superseded by the published corpus.** Preserve its saved files as a record of the interrupted run.

The authorized LLMTech run obtained extraction responses for all 64 PDF pages. Progress is saved in `knowledge/saved_extraction_64/`, including source blocks, all 64 hash-checked images, model responses, 149 deduplicated evidence records, 19 workbook rows, seven notes, an unpublished inspection report and explicit resume instructions. At checkpoint time, 59 page stages are complete; S03 pages 12, 15, 16, 17 and S04 page 6 require retry/verification or bibliography handling. There are 75 eligible passages before publication and 67 flagged records. Source-image inspection caught legend and unit errors missed by the model verifier; explicit exclusions are retained in `knowledge/source_checks.json`. No complete corpus/index is published. The live process was stopped to preserve the checkpoint when the user reported limited Codex usage. Latest backend regression suite: 66 passed; frontend typecheck/build passed. Continue with the checkpoint README; F02 remains unfinished.

### 2026-10-17 — Resume checkpoint at 5% remaining Codex usage

**Historical checkpoint, superseded by the published corpus.** Its pending page counts and missing-pointer status were accurate when work stopped; they are not outstanding F02 tasks now.

Work stopped at the user's request to record progress. No background extraction process remains running. Preserve the earlier 64-page snapshot as an unpublished historical checkpoint.

Completed and saved:

- [x] LLMTech Qwen provider integration, provider-specific credentials/request settings, bounded retries, quota handling and runtime-only public trial credential loading.
- [x] All 64 source pages, images and received extraction responses saved in `knowledge/saved_extraction_64/`; all 19 method rows and seven notes preserved.
- [x] Numerical quantity guards, rejected-empty-cache recovery, supported-annotation selection for duplicate source spans, and source-image inspection exclusions implemented.
- [x] Verification prompt checks legend colors, printed units and band assignments; exact source blocks can contain multiple subheadings.
- [x] Bibliography handling now recognizes numbered continuations, ACS headers, acknowledgments, author contributions and conflicts of interest. Classification normalization leaves retained source text untouched. This latest fix is saved and will load on the next build.
- [x] Latest regression suite: **69 passed** in 15.34 seconds; evidence: `outputs/ingest/tests_complete.xml`. Earlier frontend typecheck/build passed. Browser verification was not completed in this resume.
- [x] Interrupted stage: `knowledge/.staging/0f44ae8e71ea4694879f80ff0fad1df4/`, containing all 64 raw pages. **55 complete response bundles matching the current verification fingerprint** remain in `outputs/ingest/cache/`. This is a cache count, not final corpus validation. The stage status file may still say `running` because the process was stopped externally; the actual process is stopped.

Remaining checkpoints, in order:

1. Resume without `--refresh`. Current-verification bundles are missing for **S03 p.15; S04 pp.1–6; S05 pp.1–2**. Most need verification of an existing extraction. The bibliography fix should resolve reference-only pages. The earlier snapshot used the previous verification prompt, explaining its different completion count.
2. Inspect remaining failures and key S02 figures on slides 6–10, 13–16 and 18. Keep uncertain/incorrect records excluded. Existing source checks exclude a reversed Raman legend and unsupported wavelength unit/band mapping. Do not imply human review or AFS approval.
3. Build local BGE embeddings, **Qdrant** and BM25 indexes, run deep source/table/artifact/index validation, then publish atomically. **`knowledge/current.json` does not exist; no complete corpus is published.**
4. Repeat an unchanged cached build; compare evidence IDs/revisions and corpus version. Verify powder/API and opaque-dairy hybrid searches and excluded-source boundaries.
5. Verify the published report, images and readiness in the browser; update live validation evidence, README and F02 checkboxes only after success. F03 onward remain separate future work.

Resume from the project root:

```powershell
.\.venv\Scripts\python.exe -m backend.ingest build --provider llmtech --public-trial
```

After successful publication:

```powershell
.\.venv\Scripts\python.exe -m backend.ingest validate
.\.venv\Scripts\python.exe -m backend.ingest build --provider llmtech --public-trial
.\.venv\Scripts\python.exe -m backend.ingest search --query "powder blend active pharmaceutical ingredient concentration"
.\.venv\Scripts\python.exe -m backend.ingest search --query "opaque dairy fat protein"
.\.venv\Scripts\python.exe -m backend.ingest report
```

Keep existing caches and the saved snapshot. Interactive Groq configuration remains unchanged. LLMTech is temporary; check its documented shutdown date before a later resume. F02 remains unfinished until publication, reproducibility, real retrieval and browser checks pass.

### 2026-10-17 — F02 cleanup and published-report verification

**Current milestone: F02 is complete; F03 is next.** Reconciled the README, pipeline contract and plan header with `corpus-4aac882441587796afe5`. Earlier Groq failures and low-usage checkpoints are explicitly historical; their raw reports and responses are preserved. The checkpoint README now points to the published report.

- [x] Published corpus retained: 64 pages, 152 passages, 81 searchable passages, 19 method rows, seven notes, 111 embedding segments, 63 flagged records and zero human-verified records. Source checks do not imply AFS approval.
- [x] Browser flow verified: local application → status refresh → **Inspect extracted knowledge** → published version. Microsoft Edge via Playwright at 1440×1000 and 390×844; Browser plugin unavailable. Page identity, meaningful content, no framework overlay, no relevant console errors and no horizontal mobile overflow pass.
- [x] Report interactions verified: 19 method rows with nine columns and S01 Table 1 p.6 provenance; all seven notes; 100 searchable records including methods; excluded business content and known source-image mismatches; empty search state; 64 raw-page choices and rendered source preview. All 64 source-image routes return HTTP 200 JPEGs. Screenshots and detailed browser receipt are stored outside the repository.
- [x] Local frontend dependencies restored with `npm ci` from the unchanged lockfile. TypeScript/production build passes. No application code, model settings, extraction prompts or record eligibility rules changed in cleanup.
- [x] Evidence, the active pointer, canonical manifests, embedding segments and BM25 data are included in the cleanup commit. Credentials, originals, source images, raw pages, HTML reports, model binaries and Qdrant binaries remain ignored and local. A fresh checkout must rebuild from separately supplied originals before readiness/search can pass.

The current completion receipt is `outputs/ingest/published_validation.json`. It records deep validation, a cached rebuild with live model calls disabled, stable corpus/evidence revisions, real hybrid searches and post-search index validation. Historical pilot receipts remain unchanged. The interactive provider remains Groq; the published corpus records the LLMTech ingestion provider. Context-aware evidence selection, the evidence API and the assessment workflow remain future features.

### 2026-10-17 — User-authorized website crawl and manual retrieval workbench

Added a separately versioned S06 website snapshot and a frontend for manually testing retrieval. The published technical corpus remains `corpus-4aac882441587796afe5` with unchanged evidence and eligibility. This is a retrieval diagnostic interface, not the F07 customer-assessment workflow.

- [x] Crawl `https://mirphotonics.com/laboratory/` and discovered same-origin HTML pages under robots rules, a 20-page/depth-two bound, request pacing, redirect/size checks and non-HTML/legal/admin exclusions. Current snapshot: `web-a7d9d24faab7300545eb`, **10 pages and 159 text records**, stored under `knowledge/web/` with URL, heading, HTML location, fetch timestamp, raw HTML hash, evidence ID and revision.
- [x] Keep website records as business context (`retrieval_eligible=false`, separate context-search eligibility), independently indexed in local Qdrant/BM25. The technical search dataset remains the default. HTML extraction and searches make zero Qwen calls and introduce no new generative model or parser dependency.
- [x] Add `GET /api/search/status` and validated `POST /api/search`: independent BM25, independent Qdrant, hybrid or comparison; technical/website/both datasets; optional keyword synonyms; limit 1–8; source metadata, raw relevance scores, matched words and best semantic segment. BM25 does not load embeddings. A shared lock serializes API vector-store access; missing embeddings/corrupt stores are distinct from invalid query input.
- [x] Add the search workbench at `http://127.0.0.1:5173/#search`: query form, method/dataset/limit selectors, three ranking columns, business-context badges, provenance expansion, source links, empty/loading/error states and exact response JSON download.
- [x] TypeScript/production build passes. **74 backend tests pass** in the final regression run (`tmp/search_web_tests.xml`). Coverage includes HTML extraction, URL/robots boundaries, snapshot integrity and stable IDs, technical/business isolation, independent search branches, concurrent Qdrant requests, query validation and embedding failures. Both the technical corpus and website snapshot pass validation after real browser queries.
- [x] Edge/Playwright browser checks at 1440×1000 and 390×844 cover real rankings for every mode, website-only/both datasets, source provenance, exact JSON download, synonyms off, keyword empty state, simulated 503/recovery and concurrent semantic requests. No unexpected console errors, framework overlay or mobile horizontal overflow. Detailed receipt/screenshots are outside Git; Browser plugin unavailable.

Primary files: `backend/web_ingest.py`, `backend/search_service.py`, `backend/main.py`, `frontend/src/SearchWorkbench.tsx`, `frontend/src/api.ts`, `tests/test_search_web.py`. Configuration adds `WEB_CORPUS_DIR`. Raw HTML and local vector binaries remain ignored; no existing checkpoint or original supplied file was overwritten. These changes are not committed automatically.

F03 remains next. F04 still needs context-based query formation, balanced evidence ledgers, bounded additional searches and the evidence-resolution endpoint. The manual comparison tool does not establish those completion gates or validate vendor claims.

### 2026-10-17 — Reusable tool contract documentation

At the user's request, documented the implemented capabilities for later pipeline/agent use in `docs/tool_contracts.md` and `docs/tool_catalog.json`, linked from the README and pipeline contract.

- [x] Catalog the existing search-status, knowledge-search, website-refresh, website-validation and technical-corpus-validation bindings.
- [x] Preserve the exact search input schema from `backend.main.SearchRequest`, mode/dataset defaults, output/provenance fields, score semantics and HTTP error mapping.
- [x] Document read-only search separately from network/write-producing crawl refresh; include CLI/Python bindings, crawl bounds, local dependencies, concurrency and timeout limitations.
- [x] Record source-scope rules and the requirement to resolve current snapshot versions at runtime rather than hardcoding checkpoint values.
- [ ] Add agent tool registration/adapters when implementing the later assessment orchestration. No tools are registered merely by adding this documentation; no runtime behavior changed in this documentation step.

### 2026-10-17 — F03 customer enquiry extraction

- Implemented `backend/models.py`, `backend/agent.py`, `POST /api/extract`, explicit LLMTech/Groq development-run overrides and exact D01/D02 enquiry fixtures without worked answers.
- Provider output pairs values with input quotes; Python creates public provenance paths and context references. Live inspection motivated checks for verbatim structured values, sample-form omissions and duplicated shared-constraint evidence.
- `python -m pytest -q --basetemp tmp/f03-final-verified`: **122 passed**. OpenAPI exposes `ExtractionRequest` and `CaseFacts`; invalid inputs, schema failures, quotes, context membership, units, shared constraints, repairs, deadlines and sanitized API failures are covered.
- User-authorized `python -m backend.smoke_extraction --provider llmtech --public-trial` runs with final `extraction-v6` passed D01/D02 and all three synthetic cases. See `outputs/extraction/review.json` for the two exact records, their hashes, checked behaviors and limitations. This is agent source comparison, not independent human validation or spectroscopy performance evidence.
- Groq failed with generated-JSON rejection and HTTP 429 request-size/rate limits; earlier records remain intact. API provider selection still follows backend configuration; the runner override does not modify `.env`.
- F03 completion gate is closed for the reviewed cases. F04 context-based retrieval is next; no extraction frontend or assessment generation was added.

### 2026-10-17 — F04 context-aware evidence retrieval

- Implemented deterministic context queries, documented domain synonyms, hybrid candidate scoring, semantic-only admission at cosine 0.65, structured method/geometry lookup, distinct-method balancing, exact deduplication and an eight-record ledger cap.
- Added one case-wide follow-up query, explicit evidence gaps, version-pinned resolution, exact PDF/figure/workbook metadata and sanitized 404/409/422/503/504 contracts. Existing manual search shares the Qdrant lock.
- `python -m pytest -q --basetemp tmp/f04-final-verified`: **145 passed**. Initial sandbox runs stalled during Windows asyncio loopback initialization; the verified suite ran with loopback available.
- `python -m backend.smoke_retrieval` and real-corpus ASGI API checks passed without provider calls. Exact outputs, hashes, source inspection and limitations are recorded in `outputs/retrieval/review.json` and `api_validation.json`. Development diagnostics are kept under ignored `tmp/f04-retrieval-development/`.
- F04 gate is closed for the tested development inputs. F05 synthesis and claim-level scientific support review remain separate work. Existing F03 working-tree changes were preserved; no commit was created.

### 2026-10-17 — F05 structured technical assessment

- Added typed scientific decisions, requirements/provenance, prioritized questions, conditional recommendations, spectral kinds, separate Raman quantities, assumptions, risks, initial experiments and deterministic source indexes.
- Added reusable `assess_case` / `synthesize_assessment`, injected providers/retrieval, a shared deadline, worker-thread retrieval, stage callbacks and reproducibility metadata. No assessment API route or frontend was added.
- Live source review motivated source-excerpt/gap assertions, request-bound IDs and single method families, conservative method-labeled wavelength bands, satisfiable schemas for absent quantities, and backend assembly of aligned references and individual-method comparisons. Extraction-v7 reinforces exact contiguous quotation without weakening validation.
- `python -m pytest -q --basetemp tmp/f05-release-check`: **191 passed**. Restricted Windows asyncio initialization required socket-enabled execution; a separate transient manifest-replacement permission failure cleared on a fresh-directory rerun.
- `python -m backend.smoke_assessment --provider llmtech --public-trial` completed fresh D01/D02 runs with final synthesis-v8. Both are provisional; exact artifacts, hashes, source comparison and limitations are in `outputs/assessment/review.json`. Earlier schema/grounding failures remain available.
- F05 is complete for these inspected development cases. Reasons can be generic and repeated excerpts remain an editorial refinement; source identity and membership do not establish arbitrary scientific entailment. Saved provider configuration and the technical corpus were not changed. F06 is next; no commit was created.

### 2026-10-18 — F06/F07 completion and implemented scope reconciliation

- F06 added feasibility completion, canonical-evidence/mechanical validation, bounded repair and the public complete/incomplete assessment API. F07 added the verified browser workflow, compact workspaces, direct clarification answers and same-run exports. Their detailed receipts and limits are recorded with the feature sections above.
- Commits `dc30202`, `645ea40` and `844a835` subsequently added shared automatic routing, the compact interface, Gemini integration, durable enquiry rounds/explainability, the History workspace and chemist/trace PDF reports. The baseline now defaults to Gemini → LLMTech → Groq, while the later live receipt records Qwen fallback success and Gemini quota failures.
- Reconciled this plan against the current code, input inventory, active corpus pointer, tracked receipts and Git history. Replaced stale F06-next guidance, recorded implemented optional work and expanded F08–F10 for the actual API/provider/history/export contracts. This reconciliation changes documentation only and makes no new provider calls or scientific-validation claims.
- **Next:** F08.1. Only D01/D02 are currently staged as development inputs; the generic runner, D03–D08 review and final-scenario input file are outstanding. The NIR/source-relevance finding remains an explicit F08 regression, and Gemini-specific comparison success remains separately unresolved.
- **F08 implementation checkpoint:** Added exact D03–D08 inputs, the API batch runner, isolated per-batch history, per-case trace JSON/PDF exports, incremental manifests and a per-case review receipt. Added a general method-rationale consistency validator and synthesis-v11 guidance; the reproduced NIR/MIR mismatch is now rejected mechanically. Automatic live batches produced complete D01–D07 and D08 results across preserved runs, while individual provider responses remain stochastic and one coherent all-eight batch still needs a clean rerun. Backend regression is **298 passed**; frontend tests (**17**) and production build pass. Semantic source review, browser rerun after this change, and Gemini quota/comparison checks remain open before F08 can close.

### 2026-10-18 — F09/F10 reproducibility increment

- Extended `evaluation/run_evaluation.py` with final-suite input preparation and exact-source verification, frozen provider/profile and corpus/index configuration identity, portable per-case evidence exports, offline manifest verification and guarded publication. Final mode always requires all six cases and will not run without the original organizer scenario file. Existing development input loading remains compatible.
- Added final-input integrity tests for H01–H06 parsing, source hashes and mutation rejection. The original `customer_scenarios_for_final_evaluation.txt` is still absent from `knowledge/original_sources/`; `evaluation/final.json` and final outputs therefore remain intentionally ungenerated.
- Updated README with fresh-start and final-run commands, automatic-routing provenance, local history/trace-export handling and the final evaluation boundary. Added an editable five-slide deck at `presentation/output/spectraplan-demo.pptx` and a timed rehearsal script at `presentation/demo_script.md`. The presentation candidate passed the bundled package, layout and first-party import checks; OneDrive rejected the finalizer hard-link, so the validated candidate was copied unchanged to the repository output.
- Verification: `python -m pytest -q tests/test_evaluation_runner.py --basetemp=tmp/pytest-f09` — **4 passed**; Python compilation passed; rendered deck slides were inspected at full size. F08 semantic review, one coherent D01–D08 rerun, fresh browser demonstration and final H01–H06 source remain open.
