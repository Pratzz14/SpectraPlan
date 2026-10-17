# SpectraPlan

SpectraPlan is a planned AI assistant for the first technical assessment of industrial spectroscopy enquiries. It will help an Art Fiber Systems (AFS) expert identify missing information, compare promising measurement approaches and design an initial feasibility experiment using the supplied AFS materials.

## Project status

**F01 is complete:** a FastAPI readiness API, a React status page and a structured Groq provider adapter are implemented. Both local services and their development API connection have been verified. On 2026-10-17, Groq `qwen/qwen3.8-27b` returned a live structured response that passed local schema and content validation.

The reviewed corpus, enquiry extraction, assessment pipeline and evaluation runner are future increments. Missing corpus readiness is expected until F02.

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
| `PROVIDER_BASE_URL` | `https://api.groq.com/openai/v1` |
| `PROVIDER_MODEL` | `qwen/qwen3.8-27b` |
| `PROVIDER_REASONING_EFFORT` | `medium`; configurable for later extraction/reasoning stages |
| `PROVIDER_CALL_TIMEOUT_S` | 30 seconds per attempt |
| `REQUEST_DEADLINE_S` | 90 seconds shared across attempts and retry delays |
| `PROVIDER_MAX_RETRIES` | 2 retries, at most 3 attempts |
| `PROVIDER_MAX_COMPLETION_TOKENS` | 4096; the small smoke test uses 2048 |
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
    "approved_passages": 0,
    "approved_methods": 0
  },
  "provider": {
    "name": "groq",
    "model": "qwen/qwen3.8-27b",
    "configured": false
  }
}
```

`ready` means local configuration and corpus prerequisites are present; it does not verify provider access or scientific correctness. `provider.configured` only indicates a non-placeholder key. Health checks never contact Groq, return credentials or expose local paths.

Corpus status is `missing`, `unreadable`, `invalid`, `empty` or `ready`. The foundation checks readable JSON, unique evidence IDs, source/revision consistency, required location fields and approved-record counts. It expects a manifest with `corpus_version` and `sources`, page-aware JSONL passages, and a JSON array of reviewed method rows. Both approved passages and method rows are required for local corpus readiness. F02 will generate and review these artifacts; no placeholder corpus is supplied, and these checks do not replace source review or later scientific validation.

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
| Retrieval | BM25 with local JSON/JSONL evidence and a structured method table |
| Generation | Configurable model provider with structured responses, bounded retries and local validation |

The backend will run extraction, retrieval, synthesis and validation. API credentials will remain on the backend. External retrieval is disabled by default in the MVP design.

## Source materials and evaluation

The supplied AFS PDFs and method comparison workbook are the primary technical references. Source locations must remain traceable to PDF pages, slides or workbook rows. Business materials and research demonstrations retain their original scope.

Organizer-supplied original files are not included in this repository. The local source location, `knowledge/original_sources/`, is ignored by Git and can be changed with `SOURCE_DIR`. Corpus rebuild instructions will be added with F02.

Development scenarios **D01–D08** and organizer worked answers are used for development and review, separately from technical retrieval. Final scenarios **H01–H06** must run through the general application pipeline. Their answers must be generated without manual editing or case-specific hardcoding.

Required final artifacts will include `outputs/H01.json` through `outputs/H06.json` and `outputs/run_manifest.json`. These outputs and the reviewed corpus are intentionally not globally ignored by Git. They have not been generated yet.

## Verification

Automated backend checks cover configuration, readiness, local structured-output validation, transient retries, deadlines and sanitized failures. Browser verification covers the real local proxy, loading, refresh and recovery, plus a simulated backend failure, at desktop and narrow widths. The live Groq smoke test passed on 2026-10-17. See the implementation plan for actual commands and results. Scientific performance has not been validated.

## License

Original SpectraPlan project content is available under the [MIT License](LICENSE).

Third-party AFS materials, research papers and any excerpts or figures derived from them retain their respective rights and are not relicensed by this repository's MIT License.
