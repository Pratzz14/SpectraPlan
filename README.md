# SpectraPlan

SpectraPlan is a planned AI assistant for the first technical assessment of industrial spectroscopy enquiries. It will help an Art Fiber Systems (AFS) expert identify missing information, compare promising measurement approaches and design an initial feasibility experiment using the supplied AFS materials.

## Project status

**F01–F04 are complete for their tested development gates:** a FastAPI readiness API, a React status page, structured provider adapters, backend enquiry extraction, and context-aware hybrid evidence retrieval are implemented. Both local services and their development API connection have been verified. On 2026-10-17, Groq `qwen/qwen3.8-27b` returned the initial live provider smoke response, the complete 64-page F02 corpus was published and validated, and F03 extraction was checked with LLMTech.

F02 adds source inventory, page-aware Qwen extraction and verification, workbook import, a manual inspection report, and Qdrant + BM25 search. The active corpus is `corpus-4aac882441587796afe5`, with 152 passages, 81 retrieval-eligible passages, 19 method rows and 63 flagged records. F03 adds typed enquiry extraction and `POST /api/extract`, with exact input provenance, separate streams, explicit unknowns and attributed customer claims. Assessment generation and full evaluation remain future increments. See [customer extraction](docs/customer_extraction.md) for its API, provider options and checks.

F04 adds `POST /api/retrieve` and revision-pinned `GET /api/evidence/{evidence_id}`. It combines BM25, local BGE/Qdrant semantic search and structured method lookup into at most eight evidence records, exposing selection reasons, scores, context coverage and remaining gaps. See [evidence retrieval](docs/evidence_retrieval.md) for the API, semantic threshold, single follow-up budget and verification records.

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

If `.env` already exists, keep it and compare it with `.env.example` instead of overwriting it. Set `GROQ_API_KEY` in the root `.env` when available. Keep the key on the backend; never put it in a `VITE_*` variable or commit it. The supplied placeholder is treated as missing configuration.

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

### Configuration

Environment variables override the root `.env`. Relative paths resolve from the repository root, independently of the current working directory. Restart the backend after changing configuration.

| Variable | Default / purpose |
|---|---|
| `GROQ_API_KEY` | Backend-only key; supply locally in `.env` or the environment |
| `LLMTECH_API_KEY` | Backend-only LLMTech key; ingestion can explicitly use the documented public trial |
| `PROVIDER_NAME` | `groq` or `llmtech`; CLI ingestion override leaves interactive configuration unchanged |
| `PROVIDER_BASE_URL` | `https://api.groq.com/openai/v1` |
| `PROVIDER_MODEL` | `qwen/qwen3.8-27b` |
| `PROVIDER_REASONING_EFFORT` | `medium`; configurable for later extraction/reasoning stages |
| `PROVIDER_CALL_TIMEOUT_S` | 30 seconds per attempt |
| `REQUEST_DEADLINE_S` | 90 seconds shared across attempts and retry delays |
| `PROVIDER_MAX_RETRIES` | 2 retries, at most 3 attempts |
| `PROVIDER_MAX_COMPLETION_TOKENS` | 4096; the small smoke test uses 2048 |
| `EXTRACTION_MAX_COMPLETION_TOKENS` | 3072; F03 output ceiling, also capped by the provider ceiling |
| `SOURCE_DIR` | `knowledge/original_sources` |
| `CORPUS_DIR` | `knowledge` |
| `SMOKE_OUTPUT_DIR` | `outputs/provider_smoke` |

Groq documents [strict structured outputs](https://console.groq.com/docs/structured-outputs) for the selected model. The adapter requests a strict JSON Schema and validates content again with Pydantic. A successful response must finish normally, contain JSON matching the supplied model and pass local type/field checks. There is no automatic model/format fallback or content-repair call in F01.

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
npm run build
npm ls --depth=0
Pop-Location
```

`requirements.txt` pins the installed Python environment including transitive dependencies; `frontend/package-lock.json` records the npm dependency tree. Key installed versions:

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

Continue using the implementation plan's task checklists and progress log. The proposed MVP budget is 12 hours; it is a project planning choice.

## Planned workflow

1. Enter a customer enquiry in natural language.
2. Extract stated facts, unknowns and distinct process streams while preserving input provenance.
3. Retrieve reviewed AFS passages and method-table evidence.
4. Produce conditional method and measurement concepts, prioritized questions, limitations and a practical first experiment.
5. Inspect claim-level source references and export the generated assessment with its evidence and run metadata.

The assistant supports expert review. Its recommendations are hypotheses to test; the software does not establish measurement accuracy, equipment compatibility or clinical readiness. A justified insufficient-information assessment is a valid result.

## Planned architecture

| Layer | Proposed implementation |
|---|---|
| Interface | React, TypeScript, Vite and Tailwind |
| API and validation | Python 3.11+, FastAPI and Pydantic v2 |
| Document ingestion | PyMuPDF and openpyxl |
| Retrieval | Local Qdrant + BM25 with BGE-small embeddings and canonical JSON/JSONL evidence |
| Generation | Configurable model provider with structured responses, bounded retries and local validation |

The backend will run extraction, retrieval, synthesis and validation. API credentials will remain on the backend. External retrieval is disabled by default in the MVP design.

## Source materials and evaluation

The supplied AFS PDFs and method comparison workbook are the primary technical references. Source locations must remain traceable to PDF pages, slides or workbook rows. Business materials and research demonstrations retain their original scope.

Organizer-supplied original files are not included in this repository. The local source location, `knowledge/original_sources/`, is ignored by Git and can be changed with `SOURCE_DIR`. See the F02 commands below.

Development scenarios **D01–D08** and organizer worked answers are used for development and review, separately from technical retrieval. Final scenarios **H01–H06** must run through the general application pipeline. Their answers must be generated without manual editing or case-specific hardcoding.

Required final artifacts will include `outputs/H01.json` through `outputs/H06.json` and `outputs/run_manifest.json`. These outputs and the reviewed corpus are intentionally not globally ignored by Git. They have not been generated yet.

## Verification

Automated backend checks cover configuration, readiness, local structured-output validation, transient retries, deadlines and sanitized failures. Browser verification covers the real local proxy, loading, refresh and recovery, plus a simulated backend failure, at desktop and narrow widths. The live Groq smoke test passed on 2026-10-17. See the implementation plan for actual commands and results. Scientific performance has not been validated.

## License

Original SpectraPlan project content is available under the [MIT License](LICENSE).

Third-party AFS materials, research papers and any excerpts or figures derived from them retain their respective rights and are not relicensed by this repository's MIT License.

## F02 — Knowledge extraction and inspection

Run from the repository root with the configured backend-only provider key. The verified published build used the documented LLMTech public-trial ingestion override; interactive provider configuration remains unchanged:

```powershell
.\.venv\Scripts\python.exe -m backend.ingest pilot --provider llmtech --public-trial
.\.venv\Scripts\python.exe -m backend.ingest build --provider llmtech --public-trial
.\.venv\Scripts\python.exe -m backend.ingest validate
.\.venv\Scripts\python.exe -m backend.ingest report
.\.venv\Scripts\python.exe -m backend.ingest search --query "powder blend API concentration"
.\.venv\Scripts\python.exe -m backend.ingest search --query "opaque dairy fat protein"
```

The pilot processes S01 p.10 and S02 p.6 and prints an **unpublished** HTML report location. A full build processes all 64 pages from S01–S05, imports 19 workbook rows and seven notes, and publishes only after validation and indexing succeed. Text and rendered page images are sent to the selected ingestion provider for extraction and separate verification. The PDF build preserves S06 as a link; the separately authorized website crawl below stores its own business-context snapshot. Development examples, final evaluation inputs, the challenge brief, unknown files and business context never enter default technical retrieval.

The extractor uses strict JSON schemas and versioned prompts in `backend/prompts/`. Qwen selects source block IDs; code copies original text and records quote offsets and page bounds. Visual transcriptions carry a labeled region and remain distinct from verbatim text. Structured facts and quantities retain exact supporting quotes. Ambiguous or unsupported candidates are inspectable but excluded from search.

No approval workflow is required. After a successful build, open **Inspect extracted knowledge** in the application or [the report endpoint](http://127.0.0.1:5173/api/knowledge/report). `report` prints the standalone HTML location, which also works locally with the adjacent page assets. Filter by source, physical PDF page, content kind, validation status or retrieval eligibility. Inspect the passage, facts, source image with highlighted regions, workbook cells, original notes and complete provenance. Records default to `human_review_status="not_reviewed"`; automated validation does not establish scientific accuracy.

The current standalone report is [the published corpus report](knowledge/versions/corpus-4aac882441587796afe5/review.html). The earlier `knowledge/saved_extraction_64/review.html` is a historical, unpublished checkpoint and does not show the final counts. The report and adjacent images are generated local files; rebuild them after a fresh checkout.

### Models, limits and storage

- Extraction and verification: configurable Qwen provider. The published F02 build used LLMTech `nvidia/Qwen3.8-27B-NVFP4`, an 8192-token extraction ceiling, up to 2048 verification tokens and two concurrent page jobs. Groq retains its separate conservative defaults and pacing; interactive F01 provider settings remain unchanged. An incomplete structured response is rejected, never silently repaired or published.
- Embeddings: local `BAAI/bge-small-en-v1.5` through FastEmbed, 384 dimensions, cosine similarity. The first use downloads public model files to `outputs/embedding_models/`; their checksums are captured in each index manifest. Source content is embedded locally. Each segment is explicitly checked below the model's 512-token limit, including its heading. Long indivisible sentences fail clearly rather than truncate.
- Retrieval: up to 20 BM25 candidates and 20 Qdrant candidates, fused with reciprocal rank fusion (`k=60`) into at most eight unique evidence records. A domain-only synonym map covers terms such as MIR/FTIR and moisture/water. Results are candidates for a later assessment stage, not scientific endorsements. No cross-encoder reranker is used.
- Qdrant: persistent local Python-client mode, no Docker/cloud account. The CLI opens and closes the active database per search. Do not access one local database from multiple processes simultaneously; concurrent searches contend for the local lock. Each build creates a separate generation; API report routes use versioned assets, so a rebuild cannot mix source images between reports.

### Rebuild and failure behavior

`build` reuses content-addressed extraction and verification caches. Source hashes, schema and prompt hashes, extraction version, rendered-image hash, provider settings and output contents determine provenance and revisions. `build --refresh` explicitly reruns model stages and creates a new revision when outputs differ. Identical cached builds retain evidence IDs, record revisions and corpus version. Evidence IDs use source/page/content identity; workbook IDs use sheet/row and retain S01 Table 1 p.6 as the underlying citation. Qualitative ratings and optical path/depth remain source values, not equipment guarantees or remote fiber lengths.

Canonical data lives in `knowledge/versions/<corpus-version>/`. `knowledge/current.json` is replaced atomically only when extraction, validation, report creation and both indexes finish successfully. Root-level `source_manifest.json`, `passages.jsonl`, `methods.json`, `method_notes.json` and `validation_report.json` are convenience exports; readers use the version pointer. Prior generations survive failed builds. Working stages remain under `knowledge/.staging/`, with sanitized failure diagnostics; completed model stages remain cached under `outputs/ingest/cache/`. Rerun the same build to resume. Rate limits receive bounded waits; exhausted waits or schema failures leave the published corpus untouched.

Originals, model binaries, page images, raw extraction caches and Qdrant binaries are local rebuildable artifacts. Keep the original-source folder available when validating or rebuilding. Generated evidence and manifests remain trackable. Their third-party source rights remain unchanged.

A fresh checkout includes the published evidence, manifests, segments and BM25 data, but requires a local rebuild before readiness or search can pass: source images, raw pages, the HTML report, model files and Qdrant binaries are deliberately excluded from Git. Rebuild with the separately supplied originals and the selected provider. An existing local cache avoids repeating successful model stages; `--refresh` intentionally reruns them.

See [the pipeline contract](docs/knowledge_pipeline.md) for exact outputs, interfaces, validation and current live-run status.

### F02 live validation status (2026-10-17)

The active corpus is **`corpus-4aac882441587796afe5`**: all 64 PDF pages processed, 152 passages, 81 eligible passages, 19 eligible method rows, seven notes, 111 embedding segments and 63 flagged records excluded from retrieval. Human-verified records remain zero; no AFS approval is implied.

Deep validation passes against the original sources, workbook cells, page-image hashes and Qdrant/BM25 membership. Replaying all 64 cached responses exactly reproduces the 152 published records. Representative powder/API and opaque-dairy searches exercise both retrieval branches; backend regression tests pass (69 tests). Context-aware evidence selection remains F04 work: generic search can still return biomedical material for a dairy query.

`outputs/ingest/published_validation.json` records current completion checks. `outputs/ingest/live_validation.json` retains the earlier failed Groq pilot as historical evidence; it is not the active corpus status. Readiness is local configuration/index readiness, not a live provider check or scientific endorsement. F03 customer-enquiry extraction is documented [separately](docs/customer_extraction.md).

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

`GET /api/search/status` reports technical and website dataset readiness. `POST /api/search` accepts `query` (1–2000 characters), `mode` (`compare`, `bm25`, `qdrant`, `hybrid`), `dataset` (`technical`, `website`, `all`), `limit` (1–8) and `expand_synonyms`. Semantic queries must fit 512 tokenizer tokens. Missing/corrupt datasets or a busy vector store return a sanitized 503; invalid inputs return 422. The manual search API remains separate from `POST /api/extract`; context-based evidence retrieval, assessment generation and an evidence-resolution endpoint remain F04–F06 work.
