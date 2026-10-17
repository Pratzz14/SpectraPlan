# SpectraPlan Iterative Implementation Plan

**Based on:** [Technical specification v1.1](spec.md)\
**Status:** F01 complete, including live-provider verification; F02 next\
**Structure:** Main feature → tasks → subtasks\
**Target:** A working, source-grounded spectroscopy assessment app with reproducible evaluation outputs.

## How to use this plan

Work through the main features in order. Each task has a stable ID so you can request a small increment, such as “Implement F02.2,” or a complete feature, such as “Implement F04 and verify its completion gate.” Check off a subtask only after its work is complete; check off a parent task only when all its subtasks are complete.

At the end of each iteration, record the files changed, checks performed, remaining issues and next task in the progress log. Keep a feature unfinished if its completion gate has not passed. Distinguish source inspection, automated tests, live model calls and browser verification; one does not establish the others.

The specification remains the authority for contracts and behavior. This plan breaks that work into increments; it does not introduce permission to change scientific requirements or fabricate missing evidence. Checkmarks below reflect recorded implementation evidence; unresolved gates remain open.

## Implementation sequence

The timeboxes are the specification's proposed 12-hour budget, not guaranteed estimates. They include the checks within each feature. If a completion gate takes longer, reduce optional scope rather than marking unfinished work complete.

| Order | Main feature | Depends on | Target time | Observable result |
|---|---|---|---:|---|
| F01 | Project foundation and provider connection | None | 0.5 h | Backend, frontend and model smoke test run |
| F02 | Reviewed AFS knowledge base | F01 | 1.5 h | Inspectable passages and method rows with provenance |
| F03 | Customer enquiry extraction | F01 | 1.25 h | Facts, unknowns and separate contexts from an enquiry |
| F04 | Evidence retrieval | F02, F03 | 1 h | Relevant evidence ledger for each enquiry |
| F05 | Structured technical assessment | F04 | 1.25 h | First provisional assessment from the real pipeline |
| F06 | Feasibility planning and validated API | F05 | 1.5 h | Complete API result with checks and bounded failures |
| F07 | Assessment interface and export | F06 | 2 h | Browser input → assessment → evidence → JSON |
| F08 | Development evaluation and fixes | F07 | 1.5 h | Reviewed D01–D08 results and tested failure paths |
| F09 | Reproducible final evaluation | F08 | 1 h | Six generated final outputs and run manifest |
| F10 | Reproducible setup and demonstration | F09 | 0.5 h | Fresh-start instructions, slides and demo |
| | **Total** | | **12 h** | |

**First useful milestone:** F02–F05 support a real enquiry through extraction, retrieval and synthesis using a small reviewed corpus. F06 makes that result suitable for the public API; F07 makes the complete workflow usable in the browser. Keep the initial corpus small enough to review, then expand its coverage before development evaluation.

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

**Observed F01 status (2026-10-17): Complete.** Local services, readiness API, development proxy and browser checks pass. Selected provider: Groq `qwen/qwen3.8-27b`, with configurable medium reasoning and strict JSON Schema plus local Pydantic validation. After the key was supplied locally, the [successful live smoke record](../../outputs/provider_smoke/20261017T094530Z_0cb5a2339fbc465d895e14d32f6745ea.json) captured `sample_phase="powder"` and `target="moisture"`, with local schema/content validation and exit 0. The [earlier missing-key attempt](../../outputs/provider_smoke/20261017T092630Z_d3e51022e47a4ec4ab8a9cfb114b34f3.json) is preserved. Missing corpus is expected; F02–F10 remain unimplemented.

## F02 — Reviewed AFS knowledge base

**Outcome:** A small, reproducible technical corpus with trustworthy source locations.\
**Spec:** Section 5.\
**Primary files:** `backend/ingest.py`, `knowledge/source_manifest.json`, `knowledge/passages.jsonl`, `knowledge/methods.json`.

- [ ] **F02.1 — Inventory and separate the supplied materials**
  - [ ] Map source IDs S01–S06 to their exact supplied filenames; record hashes and PDF page counts.
  - [ ] Keep challenge instructions, development examples and final evaluation inputs outside the technical retrieval corpus.
  - [ ] Classify S05/S06 as business context and configure source locations without hardcoded Downloads paths.

- [ ] **F02.2 — Extract and review page-level evidence**
  - [ ] Extract S01–S05 text with 1-based page numbers and headings, then form coherent passages without separating quantities from labels or units.
  - [ ] Start with evidence needed for D01/D02; expand to the remaining methods, application families and research limitations before F08.
  - [ ] Inspect relevant S02 visuals, especially slides 6–10, 13–16 and 18, and label reviewed figure transcriptions separately from verbatim text.
  - [ ] Assign stable evidence IDs, source location, content kind, evidence scope, revision and project review status; exclude unreviewed records from the active corpus.

- [ ] **F02.3 — Import the method comparison table**
  - [ ] Parse all 19 method/geometry rows from the workbook and preserve the notes sheet.
  - [ ] Retain method, geometry, sample type, physical phenomenon, path/depth, qualitative ratings and workbook sheet/row provenance.
  - [ ] Give rows stable evidence IDs and retain their underlying citation to S01 Table 1, page 6.
  - [ ] Preserve the distinction between optical path/depth and fiber-link length; do not convert qualitative ratings into product guarantees.

- [ ] **F02.4 — Verify ingestion**
  - [ ] Check representative passage text, page numbers and visual transcriptions against the original sources.
  - [ ] Test page numbering, unique evidence IDs, method-row parsing and exclusion of nontechnical/evaluation content.
  - [ ] Confirm rebuilding unchanged sources preserves the intended IDs and revision metadata; document how to rebuild the corpus.

**Completion gate:** The corpus contains no placeholders, every active record resolves to a reviewed source location, and table ingestion preserves all rows and provenance. Project review status must not imply AFS approval.

## F03 — Customer enquiry extraction

**Outcome:** Typed customer facts with unknowns and multiple process streams preserved.\
**Spec:** Sections 6.1 and 9.2.\
**Primary files:** `backend/models.py`, `backend/agent.py`, `tests/`.

- [ ] **F03.1 — Define fact and provenance models**
  - [ ] Implement `CaseFacts`, `MeasurementContext`, `CustomerStatement` and fact-provenance records with safe collection defaults.
  - [ ] Represent reported facts, requested outcomes, proposed approaches and customer claims separately.
  - [ ] Preserve exact supporting input quotes, context IDs, raw ranges and units; use `null` for unknown values.

- [ ] **F03.2 — Implement structured extraction**
  - [ ] Write a versioned extraction prompt that records only what the customer states and does not recommend a method.
  - [ ] Separate distinct streams/targets into contexts and preserve shared constraints without inventing per-stream facts.
  - [ ] Parse and validate extraction output; reject malformed structures and untraceable input quotes.
  - [ ] Expose extraction through a callable pipeline stage; add `/api/extract` only if useful for development.

- [ ] **F03.3 — Check extraction behavior**
  - [ ] Verify D01/D02 produce the stated sample properties, targets and unknowns.
  - [ ] Test a synthetic multi-stream enquiry and a customer assertion of an unproven instrument capability.
  - [ ] Test missing numerical values and ambiguous units; confirm they do not become assumed defaults or unsupported conversions.

**Completion gate:** Extracted facts trace to the enquiry, separate streams remain separate, and customer requests cannot silently become verified technical capabilities.

## F04 — Evidence retrieval

**Outcome:** A bounded, inspectable evidence set that supports the assessment.\
**Spec:** Sections 5 and 9.1.\
**Primary files:** `backend/retrieval.py`, `tests/`.

- [ ] **F04.1 — Implement lexical search**
  - [ ] Build BM25 over reviewed technical passages and expose a deterministic search function.
  - [ ] Form queries from each context's target, matrix, process, requested method and consequential unknowns.
  - [ ] Add a small documented domain synonym map where needed; exclude scenario IDs and scenario-specific phrase matching.

- [ ] **F04.2 — Combine passages and method rows**
  - [ ] Retrieve relevant method-table rows alongside passages and place both in one evidence ledger.
  - [ ] Deduplicate and balance support across contexts, geometry, compatibility and limitations where relevant.
  - [ ] Target four to eight meaningful records, with eight as the total cap; never pad weak results.
  - [ ] Permit one additional targeted/broadened search and expose any remaining evidence gap.

- [ ] **F04.3 — Implement evidence resolution**
  - [ ] Resolve evidence IDs to the exact source revision, file, page, reviewed text/transcription and optional workbook locator.
  - [ ] Implement `/api/evidence/{evidence_id}` using the allowlisted corpus rather than arbitrary file paths.
  - [ ] Test relevant retrieval on development enquiries, missing support, unknown IDs and unreviewed records.

**Completion gate:** A developer can inspect why each returned record is relevant. A successful empty search is distinguishable from a broken index, and table evidence has the same traceability as PDF evidence.

## F05 — Structured technical assessment

**Outcome:** A real first assessment with conditional method choices, questions and source-backed reasoning.\
**Spec:** Sections 6.2, 9.3 and 5.1.\
**Primary files:** `backend/models.py`, `backend/agent.py`.

- [ ] **F05.1 — Define the assessment contract**
  - [ ] Implement requirements, prioritized questions, recommendations, spectral ranges, assumptions, risks and experiment fields from the specification.
  - [ ] Define scientific decision statuses and their required reasons; allow an empty shortlist for justified insufficient-information/outside-scope outcomes.
  - [ ] Model technical assertions with `text` and `evidence_ids`; preserve context references throughout the assessment.

- [ ] **F05.2 — Implement evidence-grounded synthesis**
  - [ ] Supply extracted facts and the retrieved evidence ledger to a versioned synthesis prompt.
  - [ ] Generate a concise conditional shortlist, useful clarification questions and high-level measurement concepts.
  - [ ] Distinguish nominal spectral range from usable equipment coverage, and Raman excitation from Raman shift.
  - [ ] Keep customer assumptions, source limitations and contradictory evidence visible; treat document text as data rather than executable instructions.

- [ ] **F05.3 — Build the first working backend flow**
  - [ ] Connect extraction → retrieval → synthesis through one reusable assessment pipeline.
  - [ ] Run D01 and D02 through that pipeline with the real provider and reviewed corpus.
  - [ ] Inspect the resulting method choices, questions and citations against the source material; correct general prompt/retrieval issues.

**Completion gate:** The pipeline produces a typed provisional result with source-supported reasoning for a development enquiry. Treat it as a development result until F06 validation and failure handling are complete.

## F06 — Feasibility planning and validated API

**Outcome:** A complete assessment API with a practical first experiment and explicit failure behavior.\
**Spec:** Sections 6.3, 7 and 9.3–9.4.\
**Primary files:** `backend/agent.py`, `backend/validation.py`, `backend/main.py`, `backend/models.py`, `tests/`.

- [ ] **F06.1 — Complete feasibility-study output**
  - [ ] Generate objective, representative samples/process states, independent reference measurements and relevant variation to cover.
  - [ ] Compare suitable individual methods before combinations, aligning sample location and timing where needed.
  - [ ] Propose independent validation at the batch/run/specimen/patient level appropriate to the task; avoid treating repeated scans as independent samples.
  - [ ] Tie go/no-go criteria to customer requirements, leave missing thresholds open, and label proposed experimental settings as proposals.
  - [ ] For an undefined target, propose initial characterization and clarification before analyte calibration or an exact configuration.

- [ ] **F06.2 — Implement mechanical validation and bounded repair**
  - [ ] Validate schemas, context IDs, input-quote provenance and every evidence reference against the retrieved reviewed ledger.
  - [ ] Check provenance for structured quantities and explicit configured conflicts; do not claim these checks prove arbitrary scientific prose.
  - [ ] Permit one repair attempt using specific errors and the same evidence set within the total request deadline.
  - [ ] Construct the final source index and run metadata on the backend; include all cited evidence records in the exportable envelope.

- [ ] **F06.3 — Expose the assessment contract**
  - [ ] Implement `POST /api/assess` with blank/oversized input validation and the default 8,000-character limit.
  - [ ] Return the run envelope with validated facts, assessment, errors, model identity and prompt/corpus/pipeline versions.
  - [ ] Separate `run_status` from scientific `decision_status`; incomplete results have `assessment=null` and a failed-stage error.
  - [ ] Implement the specified HTTP error mapping, per-call limits and shared deadline across retries, search and repair.

- [ ] **F06.4 — Verify successful and failing runs**
  - [ ] Exercise valid D01/D02 assessments and a justified empty-shortlist assessment.
  - [ ] Test nonexistent evidence, missing provenance, invalid model JSON, exhausted repair, provider timeout and unavailable corpus.
  - [ ] Verify an evidence gap can yield a complete cautious assessment while infrastructure failures remain incomplete/error states.

**Completion gate:** The API returns a validated, inspectable complete result or the documented incomplete/error contract. Failed synthesis cannot appear as a normal technical recommendation.

## F07 — Assessment interface and export

**Outcome:** A responsive page for entering enquiries, reviewing evidence and saving actual results.\
**Spec:** Sections 3 and 8.\
**Primary files:** `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/components/`.

- [ ] **F07.1 — Build the enquiry and request flow**
  - [ ] Add a labeled enquiry textarea, Analyze action and blank-input prevention.
  - [ ] Define matching TypeScript contracts and connect to `/api/assess`.
  - [ ] Implement empty, loading, success, incomplete and error views with useful stage/error text.
  - [ ] Prevent stale requests from replacing newer results and disable stale copy/download actions during reassessment.

- [ ] **F07.2 — Render the assessment**
  - [ ] Build requirements, clarification, recommendation and experiment components.
  - [ ] Separate facts, unknowns and assumptions, grouping stream-specific content by context.
  - [ ] Display decision reason, conditional status, geometry, qualified range and limitations without fabricated confidence percentages.
  - [ ] Render empty-shortlist and research-only/outside-scope assessments with their useful questions and next steps.

- [ ] **F07.3 — Add evidence inspection and export**
  - [ ] Make claim-level citation controls open an evidence drawer with source location, scope and reviewed content.
  - [ ] Label figure transcriptions and workbook-derived evidence accurately.
  - [ ] Download the actual run envelope with resolved evidence and metadata; copy report text derived from the same result.
  - [ ] Support editing the original enquiry and submitting it again as the required clarification workflow.

- [ ] **F07.4 — Verify the browser workflow**
  - [ ] Run a live enquiry from input through result, evidence inspection and JSON download.
  - [ ] Inspect desktop and narrow layouts, keyboard access, readable result sections and visible errors.
  - [ ] Confirm the downloaded envelope matches the displayed run; exercise resubmission, empty shortlist and a failed request.

**Completion gate:** A user can complete the entire browser workflow, inspect support for a claim and export the same run. Record browser evidence separately from backend-only tests.

## F08 — Development evaluation and fixes

**Outcome:** General pipeline problems are found and corrected before final evaluation.\
**Spec:** Section 10 and the acceptance checklist in section 14.\
**Primary files:** `evaluation/development.json`, `evaluation/run_evaluation.py`, `tests/`, `outputs/development/`.

- [ ] **F08.1 — Prepare a generic development runner**
  - [ ] Preserve D01–D08 enquiry wording as development inputs; keep organizer worked answers available only for review.
  - [ ] Invoke the same assessment pipeline used by the UI, saving machine-produced envelopes and run outcomes.
  - [ ] Keep case IDs in runner bookkeeping, not model input or runtime branching.

- [ ] **F08.2 — Review development results**
  - [ ] Compare D01/D02 with organizer worked examples for structure, caution and experiment quality without requiring identical wording or method rankings.
  - [ ] Run and inspect D03–D08 for coverage, matrix/geometry handling, target/proxy distinctions and research scope.
  - [ ] Check important claims against cited passages and log unsupported claims, critical missing questions and feasibility-plan weaknesses.
  - [ ] Fix general retrieval, schema or prompt issues and rerun affected development cases; expand reviewed evidence where justified.

- [ ] **F08.3 — Complete regression and failure checks**
  - [ ] Test a novel enquiry plus generic multi-stream, unspecified-target and unsupported-premise inputs.
  - [ ] Confirm input text and retrieved documents cannot override workflow rules or introduce arbitrary tools/URLs.
  - [ ] Run relevant contract/integration tests and repeat the browser smoke flow after material changes.
  - [ ] Record human review, stubbed tests, live provider results and browser verification separately; unresolved material issues remain open.

**Completion gate:** All eight development cases have recorded outcomes, critical fabricated claims discovered in review are resolved, and the generic pipeline handles uncertainty and failures honestly. Schema success alone is not a zero-unsupported-claims result.

## F09 — Reproducible final evaluation

**Outcome:** Six unedited application-generated final answers with traceable configuration.\
**Spec:** Sections 2 and 10.1.\
**Primary files:** `evaluation/final.json`, `evaluation/run_evaluation.py`, `outputs/H01.json`–`outputs/H06.json`, `outputs/run_manifest.json`, `outputs/runs/`.

- [ ] **F09.1 — Freeze the general pipeline**
  - [ ] Preserve the exact H01–H06 enquiry text from the supplied file and verify the stored inputs against it.
  - [ ] Record model/configuration identity, prompt hash/version, corpus hash/version and implementation revision.
  - [ ] Inspect runtime prompts, retrieval data, synonym maps and code for evaluation-case text, IDs or answer lookups; remove any case-specific behavior.

- [ ] **F09.2 — Generate and record all six outputs**
  - [ ] Run every final enquiry through the same pipeline as the UI, using IDs only to associate inputs with output filenames.
  - [ ] Save each full machine-produced envelope without manual answer editing.
  - [ ] Write a manifest containing input text or verifiable hashes, timestamps, configuration identity, output paths and run outcomes.
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
  - [ ] Document installation, source placement, corpus rebuild, model configuration, startup, checks and evaluation commands.
  - [ ] Explain the pipeline, source handling, citation scope, uncertainty behavior and known limitations.
  - [ ] Document external sources if any, keep external retrieval disabled by default, and avoid publishing supplied originals unless redistribution is established.
  - [ ] Verify a fresh setup using the instructions and confirm that credentials are absent from tracked files and outputs.

- [ ] **F10.2 — Prepare the five-minute demonstration**
  - [ ] Create concise slides covering the customer problem, workflow, architecture, evaluation and limitations.
  - [ ] Rehearse a development/novel enquiry through facts, recommendations, evidence and feasibility plan, followed by a contrasting uncertainty case.
  - [ ] Time the presentation to five minutes or less and verify the live demo environment; label any saved fallback output as a prior run.

- [ ] **F10.3 — Close the implementation checklist**
  - [ ] Review every acceptance item in specification section 14 against actual evidence.
  - [ ] Record completed features, deferred optional items and remaining limitations in the progress log and README.
  - [ ] Confirm required code, reproducibility instructions, final outputs, manifest and presentation materials are present.

**Completion gate:** The documented fresh-start workflow works, required artifacts are present, and the demonstration makes claims supported by observed results.

## Optional work after the required workflow

These items do not block the MVP. Keep them deferred until the required completion gates pass.

- [ ] **O01 — Structured fact editing:** add context-aware user corrections, preserve correction provenance, reject unknown fields and rerun affected pipeline stages.
- [ ] **O02 — Extraction endpoint:** expose `/api/extract` if the callable stage used during development was sufficient initially.
- [ ] **O03 — Additional retrieval capability:** consider model-selected search or hybrid retrieval only after the deterministic pipeline is evaluated.
- [ ] **O04 — Later product features:** separately plan persistent cases, expert review history, verified hardware catalog, spectral-data analysis and PDF export.

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

| Date | Task IDs | Status | Files changed | Verification and outcome | Remaining issue / next task |
|---|---|---|---|---|---|
| 2026-10-17 | F01.1, F01.2 configuration/adapter, F01.3 | Local foundation verified; live gate open | Backend configuration/health/provider/smoke modules; frontend; pinned dependencies; `.env.example`; ignore rules; tests; README | `python -m pytest -q --basetemp=tmp/pytest-runtime`: 50 passed; `python -m pip check`: no broken requirements; `npm run build`: typecheck and Vite build passed; direct backend and Vite-proxied `/api/health`: HTTP 200, service running, ready false; ignore checks preserve required outputs | API key not supplied; F01.2 live response unresolved |
| 2026-10-17 | F01.3 browser verification | Passed | React readiness page and Vite proxy | Installed Chrome via bundled Playwright (Browser plugin unavailable), 1440×1000 and 390×844: correct page identity, meaningful content, no framework overlay or normal console errors, loading, real proxy refresh, keyboard refresh, no horizontal overflow, simulated HTTP 503 error and recovery through the real backend. Screenshots inspected outside the repository. | Assessment workflow and scientific validation belong to later features |
| 2026-10-17 | F01.2 live smoke attempt | Unresolved dependency | Timestamped record under `outputs/provider_smoke/` | `python -m backend.smoke_provider`: exit 1, `provider_not_configured`, no model call; run ID `d3e51022e47a4ec4ab8a9cfb114b34f3` | Supply backend-only `GROQ_API_KEY`, rerun, preserve this earlier record |
| 2026-10-17 | F01.2 live provider verification; overall F01 gate | Complete | New timestamped smoke record; README; checklist | `python -m backend.smoke_provider`: exit 0; real Groq `qwen/qwen3.8-27b` response passes strict local schema and synthetic-fact checks (`powder`, `moisture`); run ID `0cb5a2339fbc465d895e14d32f6745ea`. Earlier missing-key record retained. Backend restarted; real browser refresh confirms provider configured, corpus missing and ready false, with no console errors. `.env` remains ignored; smoke records contain no API key. | F02 reviewed knowledge base; missing corpus readiness remains expected |

**Runner note:** Python asynchronous networking and the Vite proxy stalled inside the restricted Windows sandbox. Tests and both servers were verified outside it; a minimal traceback located the stall in Windows `socketpair` during event-loop creation. Workspace-local temporary paths resolved the separate `ensurepip` write restriction. These accommodations do not change application behavior.

**Suggested next iteration request:** “Implement F02 only. Complete its subtasks, verify its completion gate, update this plan with the actual results, and report any unresolved dependency.”
