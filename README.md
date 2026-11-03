# SpectraPlan

SpectraPlan is an AI assistant in development for the first technical assessment of industrial spectroscopy enquiries. It helps an Art Fiber Systems (AFS) expert identify missing information, compare promising measurement approaches and design an initial feasibility experiment using the supplied AFS materials.

## Project status

Six unedited final answers are saved in [outputs](outputs/run_manifest.json), with their original requests, frozen configuration, evidence and model traces. Offline integrity verification passes. The [scenario review](docs/scenario_content_review.md) records substantive content failures, including missed context and skipped retrieval; a complete run is not a scientifically adequate answer. See [reproducibility](docs/reproducibility.md) and the [acceptance review](docs/acceptance_review.md) for verification commands, setup evidence and remaining gaps. Demo preparation and PPTX work are deferred.

**F01–F07 are implemented for their tested development gates:** the application supports enquiry entry, source-grounded initial assessments, claim-level evidence inspection and same-run JSON/report export, alongside readiness and search tools. Both local services and their development API connection have been verified. On 2026-10-17, Groq `qwen/qwen3.8-27b` returned the initial live provider smoke response, the complete 64-page F02 corpus was published and validated, and F03 extraction was checked with LLMTech.

The former F02 pipeline produced a historical full corpus with 152 passages and 19 workbook rows. The active pipeline now uses Qwen3.7 Flash on PDF page images and Office source text, across seven sources, with readability checks, bounded retries and local text/OCR recovery. See [knowledge pipeline](docs/knowledge_pipeline.md). F03 adds typed enquiry extraction and `POST /api/extract`, with exact input provenance, separate streams, explicit unknowns and attributed customer claims. See [customer extraction](docs/customer_extraction.md) for its API, provider options and checks.

F04 adds `POST /api/retrieve` and revision-pinned `GET /api/evidence/{evidence_id}`. It combines BM25, local BGE/Qdrant semantic search and structured method lookup into at most eight evidence records, exposing selection reasons, scores, context coverage and remaining gaps. See [evidence retrieval](docs/evidence_retrieval.md) for the API, semantic threshold, single follow-up budget and verification records.

F05 provides a reusable Python assessment pipeline with conditional method choices, clarification questions, source excerpts, explicit unknowns and an initial comparison experiment. Saved development results include the complete evidence ledger and run metadata. See [technical assessment](docs/technical_assessment.md) for the Python interface and live diagnostic command. F06 adds `POST /api/assess` with complete/incomplete run envelopes, stream-specific feasibility planning, mechanical validation and bounded synthesis repair. Historical live D01/D02 checks with LLMTech returned complete provisional results at normal request limits; an undefined-target check returned complete insufficient information with an empty shortlist. F07 adds the responsive assessment interface, clarification rounds, history, evidence inspection and same-run exports. Automated checks cover backend and frontend behavior and the production build; earlier browser verification covered D01 → clarification → history/export. The full development scientific-quality gate remains open.

## Local setup

Run commands from the repository root unless a command changes directory. The verified environment is Windows PowerShell, Python **3.12.10**, Node.js **22.14.0** and npm **10.9.2**. Use Python 3.12 for the pinned Python dependencies. Vite requires Node.js 20.19+ or 22.12+ within its supported release lines.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
Push-Location frontend
npm ci
Pop-Location
```

If `.env` already exists, keep it and compare it with `.env.example` instead of overwriting it. Supply at least one of `GEMINI_API_KEY`, `LLMTECH_API_KEY` or `GROQ_API_KEY` for live assessment. Automatic routing defaults to Gemini → LLMTech → Groq; use `PROVIDER_NAME` to pin a provider. Regolo is an optional provider and is appended when its key is configured. Keep keys on the backend; never put them in `VITE_*` variables or commit them. Placeholders count as missing configuration.

Before assessing an enquiry, supply the original source files and restore the local corpus as described in [reproducibility](docs/reproducibility.md#restore-the-saved-evidence). The repository deliberately excludes source images, model binaries and the local vector database. Starting the services before restoration is useful for checking missing-dependency handling, but does not make the app ready for assessment.

On restricted Windows runners where `ensurepip` or pytest cannot write to the system temp folder, create `tmp/` and set `$env:TEMP` and `$env:TMP` to its absolute path for that shell before creating the environment. These are runner accommodations, not application requirements.

### Start the application

Backend, in one terminal at the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend, in another terminal:

```powershell
Set-Location frontend
npm run dev
```

Open [SpectraPlan](http://127.0.0.1:5173/). Vite proxies `/api` to `http://127.0.0.1:8000`; frontend code uses relative API URLs. Both services bind to loopback. Vite fails clearly if port 5173 is occupied. Stop either service with Ctrl+C in its terminal.

### Assess an enquiry

1. Enter a process description on the **Assessment** page and select **Analyze**.
2. Review customer facts and unknowns, prioritized clarification questions, conditional method options and the proposed feasibility experiment.
3. Select a citation beside a claim to inspect its exact supporting content, source location, scope and review status. Figure transcriptions and workbook rows are labeled separately.
4. Answer clarification questions directly or edit the enquiry, then select **Analyze again** for a fresh assessment. Answers are submitted alongside the original text and remain available across runs.
5. Use **Copy report** or **Download JSON** to save the displayed run. JSON includes the full response, resolved evidence ledger and metadata. Editing the draft does not change the enquiry attached to an existing result; export actions are disabled during reassessment.

A complete assessment can conclude that information is insufficient or that the request is outside the supported scope, with questions and next investigation steps. A processing failure is shown as an incomplete run with available validated facts and explicitly labeled incomplete exports. Search sources, Extracted knowledge and cached provider/corpus status remain accessible through the shared navigation. Extracted knowledge provides record filters, source-page images, provenance and separate automated/human-review labels.

Saved enquiry history links the original request, clarification questions and answers, retrieval queries and rankings, and model outputs across analysis rounds. Open **History** in the top navigation to review previous enquiries, select a round, or download its full explainability trace. Use **Continue in Assessment** to reopen a case for further work. See [enquiry history](docs/explainability.md).

### Configuration

Environment variables override the root `.env`. Relative paths resolve from the repository root, independently of the current working directory. Restart the backend after changing configuration. Automatic mode checks configured providers, caches a working choice and switches on availability failures within the shared deadline. See [provider selection](docs/providers.md) for setup, pinned modes and diagnostics.

| Variable | Default / purpose |
|---|---|
| `GROQ_API_KEY` | Backend-only key; supply locally in `.env` or the environment |
| `LLMTECH_API_KEY` | Backend-only LLMTech key; explicit setup can fill a missing key from the public trial |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Backend-only Gemini key / `models/gemini-3.8-flash` |
| `GEMINI_THINKING_LEVEL` | `medium`; `low`, `medium` or `high` |
| `PROVIDER_NAME` | `auto` (default), `gemini`, `groq` or `llmtech` |
| `PROVIDER_ORDER` | `gemini,llmtech,groq`; automatic selection priority |
| `LLMTECH_BASE_URL` / `LLMTECH_MODEL` | `https://api.llmtech.eu/v1` / `nvidia/Qwen3.8-27B-NVFP4` |
| `GROQ_BASE_URL` / `GROQ_MODEL` | `https://api.groq.com/openai/v1` / `qwen/qwen3.8-27b` |
| `PROVIDER_PROBE_TIMEOUT_S` | 8 seconds per synthetic availability probe |
| `PROVIDER_HEALTH_TTL_S` / `PROVIDER_FAILURE_TTL_S` | 300-second working cache / 30-second failure cooldown |
| `PROVIDER_REASONING_EFFORT` | `medium`; configurable for later extraction/reasoning stages |
| `PROVIDER_CALL_TIMEOUT_S` | 30 seconds per attempt |
| `REQUEST_DEADLINE_S` | 90 seconds shared across attempts and retry delays |
| `PROVIDER_MAX_RETRIES` | 2 retries, at most 3 attempts |
| `PROVIDER_MAX_COMPLETION_TOKENS` | 4096; the small smoke test uses 2048 |
| `EXTRACTION_MAX_COMPLETION_TOKENS` | 3072; F03 output ceiling, also capped by the provider ceiling |
| `ASSESSMENT_MAX_DESCRIPTION_CHARS` | 8000; enquiry limit for `POST /api/assess` |
| `SYNTHESIS_MAX_COMPLETION_TOKENS` | 4096; assessment output ceiling, also capped by the provider ceiling |
| `SOURCE_DIR` | `knowledge/original_sources` |
| `CORPUS_DIR` | `knowledge` |
| `SMOKE_OUTPUT_DIR` | `outputs/provider_smoke` |
| `EXPLAINABILITY_DB_PATH` | `outputs/assessment/explainability.sqlite`; local enquiry history |

Groq documents [strict structured outputs](https://console.groq.com/docs/structured-outputs) for the selected model. The adapter requests a strict JSON Schema and validates content again with Pydantic. A successful response must finish normally, contain JSON matching the supplied model and pass local type/field checks. Automatic availability routing preserves strict JSON Schema and local validation. Invalid generated content uses the pipeline's bounded repair path; provider selection does not establish scientific correctness.

Connection failures, timeouts, HTTP 429 and HTTP 5xx have bounded retries with 1/2-second exponential delays or `Retry-After` (capped at 10 seconds). Each attempt and delay consumes the shared deadline; an expired deadline prevents further attempts. Authentication, request/schema rejection and invalid content return explicit sanitized errors. Future pipeline stages must pass the same absolute monotonic deadline to preserve the overall request budget.

### Readiness API

`GET /api/health` returns HTTP 200 when the backend responds, including when dependencies are missing:

```json
{
  "service": "running",
  "ready": false,
  "corpus": {
    "status": "missing",
    "version": null,
    "eligible_passages": 0,
    "eligible_methods": 0,
    "flagged_records": 0,
    "human_verified_records": 0
  },
  "provider": {
    "name": "groq",
    "model": "qwen/qwen3.8-27b",
    "configured": false
  }
}
```

`ready` means local configuration and corpus prerequisites are present; it does not verify provider access or scientific correctness. `provider.configured` only indicates a non-placeholder key. Health checks never contact Groq, return credentials or expose local paths.

Corpus status is `missing`, `unreadable`, `invalid`, `empty` or `ready`. Readiness validates the published generation, checksums, source locations, eligible-record membership and matching Qdrant/BM25 metadata without calling a model. Evidence revisions are independent of the aggregate corpus version. Searchable records pass automated checks; human verification is optional. Neither status implies AFS approval.

### Verify the provider separately

After setting `GROQ_API_KEY`, run this from the repository root:

```powershell
.\.venv\Scripts\python.exe -m backend.smoke_provider
```

This explicit command makes a small live structured extraction request when configured, independently of the corpus. It validates both the schema and the two synthetic facts (`powder`, `moisture`). It saves a unique timestamped JSON record in `outputs/provider_smoke/`, exits 0 on success, and exits 1 on missing credentials or a provider/validation failure. It never runs automatically on startup, page load or health refresh. Earlier records are preserved.

The [successful live F01 smoke result](outputs/provider_smoke/20261017T094530Z_0cb5a2339fbc465d895e14d32f6745ea.json) records a locally validated extraction of `sample_phase="powder"` and `target="moisture"`. This closes F01's live-provider gate for the tested configuration. The [earlier missing-key attempt](outputs/provider_smoke/20261017T092630Z_d3e51022e47a4ec4ab8a9cfb114b34f3.json) is retained as historical evidence. Rerun this command after changing provider configuration; health checks do not repeat live verification.

### Checks and installed versions

```powershell
New-Item -ItemType Directory -Force tmp/pytest | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/pytest
.\.venv\Scripts\python.exe -m pip check
Push-Location frontend
npm test
npm run build
npm ls --depth=0
Pop-Location
```

`requirements.txt` pins backend packages; `frontend/package-lock.json` records the npm dependency tree. The setup receipt records the resolved Python environment, including SDK transitive dependencies. The websocket pin is 16.1.1 to satisfy the Google SDK's `<17` requirement; the archived final batch retains its original dependency-file snapshot. Key installed versions:

| Backend | Version | Frontend | Version |
|---|---|---|---|
| FastAPI | 0.143.3 | React / React DOM | 19.3.1 |
| Uvicorn | 0.54.0 | Vite | 8.3.4 |
| Pydantic | 2.14.1 | TypeScript | 7.0.2 |
| pydantic-settings | 2.16.0 | Tailwind / Vite plugin | 4.3.3 |
| HTTPX | 0.28.1 | React Vite plugin | 6.1.2 |
| PyMuPDF | 1.28.2 | React / React DOM types | 19.3.0 |
| openpyxl / rank-bm25 | 3.1.5 / 0.2.2 | Node types | 22.20.5 |
| pytest | 9.1.1 | | |

## Project documents

| Document | Purpose |
|---|---|
| [Technical specification](docs/plan/spec.md) | Product scope, source handling, data contracts, architecture and acceptance criteria |
| [Implementation plan](docs/plan/implementation_plan.md) | Ten ordered features with task/subtask checklists, dependencies, completion gates and a progress log |
| [Technical assessment](docs/technical_assessment.md) | Assessment API, feasibility study, validation, failure contracts and live checks |
| [Reproducibility](docs/reproducibility.md) | Restore/rebuild the corpus, inspect the archived final batch and reproduce setup checks |
| [Acceptance review](docs/acceptance_review.md) | Section-14 evidence, observed failures, deferred work and verification limits |

Continue using the implementation plan's task checklists and progress log. The proposed MVP budget is 12 hours; it is a project planning choice.

## Application workflow

1. Enter a customer enquiry in natural language.
2. Extract stated facts, unknowns and distinct process streams while preserving input provenance.
3. Retrieve reviewed AFS passages and method-table evidence.
4. Produce conditional method and measurement concepts, prioritized questions, limitations and a practical first experiment.
5. Inspect claim-level source references and export the generated assessment with its evidence and run metadata.

The assistant supports expert review. Its recommendations are hypotheses to test; the software does not establish measurement accuracy, equipment compatibility or clinical readiness. A justified insufficient-information assessment is a valid result.

## Architecture

| Layer | Implementation |
|---|---|
| Interface | React, TypeScript, Vite and Tailwind |
| API and validation | Python 3.12, FastAPI and Pydantic v2 |
| Document ingestion | PyMuPDF and openpyxl |
| Retrieval | Local Qdrant + BM25 with BGE-small embeddings and canonical JSON/JSONL evidence |
| Generation | Configurable model provider with structured responses, bounded retries and local validation |

The UI and evaluation runner both call `POST /api/assess`: customer text → typed facts → local evidence ledger → structured synthesis → mechanical validation → complete/incomplete envelope. SQLite stores enquiry rounds and traces. The evidence drawer uses the selected run's embedded ledger; JSON and PDF exports retain that run's identity. Provider credentials remain on the backend. Extraction and synthesis can use different actual providers under one automatic policy.

Technical retrieval uses the supplied PDF/workbook corpus. The optional S06 website snapshot is separately versioned business context available in the manual search workbench; ordinary assessment does not fetch the web or use that dataset as technical support. Source membership, structured-output validation and retrieval scores do not prove scientific entailment. Source-image transcriptions have automated checks, not independent expert approval.

## Source materials and evaluation

The supplied AFS PDFs and method comparison workbook are the primary technical references. Source locations must remain traceable to PDF pages, slides or workbook rows. Business materials and research demonstrations retain their original scope.

Organizer-supplied original files are not included in this repository. The local source location, `knowledge/original_sources/`, is ignored by Git and can be changed with `SOURCE_DIR`. See the F02 commands below.

Development scenarios **D01–D08** and organizer worked answers are used for development and review, separately from technical retrieval. Final scenarios **H01–H06** must run through the general application pipeline. Their answers must be generated without manual editing or case-specific hardcoding.

The development runner now accepts the exact D01–D08 inputs and invokes the same API as the UI:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --request-deadline-s 90 --call-timeout-s 30
```

Each batch records the source/input hashes, effective automatic provider policy, actual stage providers, isolated enquiry history, per-case envelopes, trace JSON/PDF files and incremental manifest under `outputs/development/`. Routine timestamped batches are ignored; retain a reviewed manifest explicitly when it becomes submission evidence. Gemini quota failures and Qwen fallback identities remain visible in the manifest; a fallback run is not a Gemini validation result.

The retained final batch is `4c14fccd1a3d4eadb672c14de91c142e`. Verify its archived artifacts without model access, originals, a live corpus or SQLite:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --verify outputs/run_manifest.json
.\.venv\Scripts\python.exe scripts/verify_submission.py --portable
```

For the original-input/runtime audit and a separate dated receipt, use `python scripts/verify_submission.py --receipt outputs/submission_verification.json`. This requires the original source at the location recorded in `evaluation/final.json`; the retained batch records the ignored repository-root copy. A fresh evaluator can use portable verification without that original.

To generate a **new** final batch, the runner requires the organizer's original `customer_scenarios_for_final_evaluation.txt`; it never reconstructs H01–H06 from development cases. In a separate evaluation workspace, place that file under `knowledge/original_sources/`, prepare exact inputs, explicitly freeze provider/model profiles and use the historical time limits below. These commands make live calls and produce new artifacts; they are unnecessary for inspecting the retained submission:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --prepare-final
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --suite final --provider auto --request-deadline-s 180 --call-timeout-s 60
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --verify outputs/runs/<batch>/manifest.json --suite final
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --publish outputs/runs/<batch>/manifest.json
```

The archived batch froze automatic routing in the order `gemini,llmtech,groq`; every extraction and synthesis stage actually completed through LLMTech, with Gemini quota failures retained in the attempt metadata. The requested Qwen model and returned `qwen38` alias are recorded separately. Normal application defaults remain 90/30 seconds. See the frozen configuration for the remaining token, repair, retrieval, prompt/schema, corpus and provider settings; the commands alone do not recreate that configuration or guarantee identical generated text.

Publication copies only a verified complete batch to `outputs/H01.json` through `outputs/H06.json` and writes `outputs/run_manifest.json`. Earlier and failed batches remain under `outputs/runs/`; individual results are not selected from different batches. Local SQLite files are ignored because portable trace and evidence exports provide the review material. These are organizer-provided evaluation scenarios, not an unseen benchmark.

## Verification

Automated backend checks cover configuration, readiness, local structured-output validation, transient retries, deadlines and sanitized failures. Browser verification covers the real local proxy, loading, refresh and recovery, plus a simulated backend failure, at desktop and narrow widths. The live Groq smoke test passed on 2026-10-17. See the implementation plan for actual commands and results. Scientific performance has not been validated.

## License

Original SpectraPlan project content is available under the [MIT License](LICENSE).

Third-party AFS materials, research papers and any excerpts or figures derived from them retain their respective rights and are not relicensed by this repository's MIT License.

## Knowledge extraction and inspection

The Qwen3.7 Flash pipeline supports all five supplied PDFs, the Excel method workbook, and the Word examples/reference document. It uses image-only PDF input, source cells/paragraphs for Office files, and lightweight readability checks with up to three attempts, then local embedded-text/PyMuPDF OCR recovery. **Extracted knowledge** shows source filters, extracted text and structured knowledge alongside PDF pages or Office content previews. Semantic inspection search includes contextual sources while assessment retrieval excludes the flyer and development examples. The corpus covers all seven sources and 72 source locations, retaining exact workbook rows alongside Qwen knowledge and clearly labelled recovered source passages.

```powershell
.\.venv\Scripts\python.exe -m backend.ingest build
.\.venv\Scripts\python.exe -m backend.ingest publish
.\.venv\Scripts\python.exe -m backend.ingest validate
```

Configure `DASHSCOPE_API_KEY` and optionally `DASHSCOPE_BASE_URL`. `build` uploads all selected PDF page images and Office source text to the configured endpoint; by default it selects all supported files. Matching completed responses are reused; `--refresh` replaces them. `publish` reuses completed latest responses without calling Qwen. Latest extraction artifacts overwrite previous attempts; publication retains only the latest Qwen generation while preserving historical evaluation corpora. See [knowledge pipeline](docs/knowledge_pipeline.md) for commands, interfaces, validation boundaries, and package organization.

The current manifest records the latest counts from all five PDFs, the method workbook, and the Word examples/reference document. Model-transcribed supporting text is not independently verified. The historical 64-page F02 results below and in archived evaluation records describe the former pipeline.

## Manual search and S06 website crawl

For later pipeline/agent integration, see the [reusable tool contracts](docs/tool_contracts.md) and [machine-readable catalog](docs/tool_catalog.json). They document the existing bindings, exact inputs/outputs, source boundaries, errors and refresh side effects. Agent tool adapters/registration are planned; the catalog does not register them automatically.

Open [the search workspace](http://127.0.0.1:5173/#search), enter keywords or a natural-language query, and choose **BM25 keywords**, **Qdrant semantic**, **Hybrid** or **Compare all**. Select the technical corpus, website context, or both. Keyword synonym expansion can be switched off for exact-term testing. Each method returns up to eight records with its own relevance score, matched words, source location, full text and provenance. Download the actual response as JSON. Scores are not confidence percentages and are not comparable across methods.

BM25 performs keyword ranking without loading embeddings. Qdrant uses the same local `BAAI/bge-small-en-v1.5` model as the published corpus; hybrid combines ranks with RRF (`k=60`). Search makes no Qwen/provider calls and does not fetch live web pages. Concurrent API requests serialize local Qdrant access; avoid a separate CLI query against the same directory at the same time.

The user-authorized S06 crawl follows same-origin HTML links from `https://mirphotonics.com/laboratory/`, with a maximum of 20 pages and link depth two by default. It respects robots rules, waits at least one second between normal page requests, rejects off-origin redirects, query URLs, legal/admin paths and non-HTML downloads, and caps each HTML response at 4 MiB. The current snapshot contains **10 pages and 159 text records**. It includes the laboratory, home/resources/news pages and discovered product/article pages within those bounds; it is not an exhaustive site archive. Images and linked PDFs are not crawled or transcribed.

HTML is parsed locally without another LLM or new parser dependency. Navigation, scripts, forms and footers are excluded. Each retained text block has its URL, page title, section heading, HTML selector, fetch timestamp, raw-snapshot SHA-256, stable evidence ID and content revision. These are vendor/business statements, not independently validated technical evidence: stored records retain `retrieval_eligible=false` for the technical corpus and `context_search_eligible=true` for the separate website collection. Website search is an explicit dataset choice. The original PDF corpus and its version are unchanged.

```powershell
.\.venv\Scripts\python.exe -m backend.web_ingest crawl --max-pages 20 --max-depth 2
.\.venv\Scripts\python.exe -m backend.web_ingest validate
```

`WEB_CORPUS_DIR` defaults to `knowledge/web`. Its `current.json` points to an immutable `versions/web-<hash>/` snapshot with a manifest, extracted pages, records, BM25/embedding segments and a local Qdrant index. Raw HTML and vector binaries are ignored by Git; extracted provenance remains trackable. A failed crawl/index build keeps the previous pointer. Existing BGE files must be present locally before indexing the website; the crawler uses local-only embeddings.

`GET /api/search/status` reports technical and website dataset readiness. `POST /api/search` accepts `query` (1–2000 characters), `mode` (`compare`, `bm25`, `qdrant`, `hybrid`), `dataset` (`technical`, `website`, `all`), `limit` (1–8) and `expand_synonyms`. Semantic queries must fit 512 tokenizer tokens. Missing/corrupt datasets or a busy vector store return a sanitized 503; invalid inputs return 422. The manual search API remains separate from `POST /api/extract`; context-based retrieval, assessment generation and pinned evidence resolution are available through `/api/retrieve`, `/api/assess` and `/api/evidence/{evidence_id}`.

### Add a new knowledge file

In Extracted knowledge, use **Add a file** to upload a PDF, XLSX, or DOCX, choose its source type, and extract it with Qwen. Progress is displayed and the new source opens after publication. The existing library is retained; the same filename updates its source.

Windows CMD equivalent, from the repository root:

```cmd
.venv\Scripts\python.exe -m backend.ingest add --file "C:\path\new-paper.pdf" --role research
```

This command sends the selected file to the configured DashScope endpoint. Add `--prepare-only` to prepare locally without uploading. See [knowledge pipeline](docs/knowledge_pipeline.md) for roles, storage and API details.
