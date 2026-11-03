# SpectraPlan

Source-grounded spectroscopy enquiry assessment, local search, extracted-knowledge inspection, and saved enquiry history.

## Setup

Windows PowerShell, Python 3.12 and Node 22.12+; run from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Push-Location frontend
npm ci
Pop-Location
```

Restore source files, embedding cache and corpus using [reproducibility](docs/reproducibility.md). Set backend credentials in `.env` only for model-powered features. Local search needs no LLM credentials.

## Start

Separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
Push-Location frontend
npm run dev
```

Open http://127.0.0.1:5173. API schema: http://127.0.0.1:8000/docs. Stop with Ctrl+C. Startup probes are disabled by default; search smoke does not start the API.

## Checks

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/pytest
.\.venv\Scripts\python.exe -m evaluation.search_smoke
Push-Location frontend
npm test
npm run lint
npm run build
Pop-Location
```

Search smoke runs four statements through BM25, embedded Qdrant and hybrid without model calls or downloads. Reports are under `outputs/search_smoke/`. Passing establishes operation, not scientific relevance.

## Code map

- Backend: `api` HTTP routes; `core` settings; `schemas` validated contracts; `providers` model adapters/routing; `services` search, knowledge and history; `pipelines` assessment/document workflows; `cli` operational commands; `prompts` instructions.
- Frontend: `app` shell; `features` assessment, search, knowledge, history and workspace; `shared` API transport and reusable UI.
- `evaluation`: saved scenario runner and offline search smoke. `tests`: isolated backend checks. `scripts`: restoration and artifact verification.

See [architecture](docs/architecture.md), [commands and services](docs/operations.md), [tool contracts](docs/tool_contracts.md), [knowledge pipeline](docs/knowledge_pipeline.md), and [quality limitations](docs/acceptance_review.md). Historical outputs and source snapshots are retained; completion does not imply expert validation.

Verification results: [refactor checks](docs/refactor_verification.md).

## Deployment boundary

The app currently targets a trusted local workstation. Keep it on loopback: it has no user authentication or tenant isolation. Embedded Qdrant uses process locks; use one backend worker. Do not run corpus publication concurrently with searches. Back up original sources, corpus generations and SQLite history together. A public deployment requires authentication, access control, HTTPS termination, and a separately designed multi-worker storage setup.

## License

Project code: [MIT](LICENSE). Third-party source materials retain their own rights.

Set `PROVIDER_PROBE_ON_STARTUP=false` for API startup without live provider probes. Assessment and ingestion actions still make their documented model calls.

Provider routing occurs on demand during model-powered actions. Set `PROVIDER_PROBE_ON_STARTUP=true` only to enable a live startup check.
