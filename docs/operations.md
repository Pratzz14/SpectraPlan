# Commands and services

All commands run from the repository root. Replace `python` with `.\.venv\Scripts\python.exe` on Windows. Credentials stay in backend environment variables.

| Service | Address/storage | Operation |
|---|---|---|
| FastAPI | 127.0.0.1:8000 | `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`; one worker |
| Vite | 127.0.0.1:5173 | `npm run dev` in frontend; proxies `/api` to backend |
| Preview | 127.0.0.1:4173 | `npm run build`, then `npm run preview` in frontend |
| Qdrant | corpus generation `qdrant/` folders | Embedded; no server or port; local cached BGE embeddings |
| BM25 | generation `bm25.json` | Local lexical ranking, no embedding load |
| History | `EXPLAINABILITY_DB_PATH` | SQLite; defaults to outputs/assessment/explainability.sqlite |
| Ingestion worker | outputs/pdf_knowledge | Spawned process; status via `/api/knowledge/ingest/status` |
| LLM providers | Gemini, LLMTech, Groq, optional Regolo | Assessment/extraction; network and credentials required |
| Knowledge extraction | DashScope-compatible endpoint | PDF/Office extraction; network and credentials required |

## CLI inventory

Run `python -m <module> --help` for option defaults. Flags below include optional and required arguments; `--help` documents required combinations.

| Module | Purpose | Arguments |
|---|---|---|
| `backend.cli.ingest` | PDF and Office knowledge ingestion: python -m backend.cli.ingest build/publish/validate/report/search. | `build`, `pilot`, `add`, `--file`, `--role`, `--name`, `--prepare-only`, `--concurrency`, `--job-file`, `publish`, `validate`, `report`, `search`, `--query`, `--refresh`, `--source` |
| `backend.cli.provider_setup` | Configure backend provider selection: python -m backend.cli.provider_setup --public-trial --check. | `--mode`, `--public-trial`, `--check` |
| `backend.cli.smoke_assessment` | Live development pipeline: python -m backend.cli.smoke_assessment --provider llmtech --public-trial. | `--case`, `--provider`, `--public-trial`, `--api`, `--request-deadline-s`, `--call-timeout-s`, `--output-dir` |
| `backend.cli.smoke_extraction` | Manual live extraction check: python -m backend.cli.smoke_extraction. | `--case`, `--output-dir`, `--provider`, `--public-trial` |
| `backend.cli.smoke_gemini_extraction` | Run the opt-in original-file extraction comparison. | `--output`, `--limit`, `--source-id` |
| `backend.cli.smoke_llmtech` | Live LLMTech provider and document-extraction checks. | `--public-trial` |
| `backend.cli.smoke_provider` | Live structured-output provider diagnostic. | `--provider`, `--all` |
| `backend.cli.smoke_retrieval` | Offline development inspection using accepted, hash-pinned F03 facts; no provider calls. |  |
| `backend.pipelines.website.ingest` | Bounded S06 same-site HTML crawl. | `crawl`, `validate`, `--max-pages`, `--max-depth` |
| `evaluation.run_evaluation` | Run development or final scenarios through the public assessment API. | `--case`, `--suite`, `--prepare-final`, `--verify`, `--publish`, `--source`, `--provider`, `--public-trial`, `--request-deadline-s`, `--call-timeout-s`, `--input`, `--output-dir` |
| `evaluation.search_smoke` | Offline operational search checks; no provider initialization or downloads. | `--input`, `--output-dir` |
| `scripts.restore_corpus` | Restore local images, report and indexes from the saved canonical evidence. | `--from-generation`, `--local-model-only` |
| `scripts.verify_submission` | Verify the saved final batch; never generate, publish or edit answers. | `--manifest`, `--portable`, `--receipt` |

Live calls: knowledge `build`/`pilot`/`add` (unless preparation-only), provider checks, assessment/extraction diagnostics, and scenario execution. Website `crawl` performs HTTP requests to the website. `publish` reuses saved extraction but may require embeddings. Restore with `--local-model-only` to forbid downloads. Search smoke uses cached embeddings only.

CLI migration: `backend.ingest` → `backend.cli.ingest`; `backend.smoke_*` → `backend.cli.smoke_*`; `backend.provider_setup` → `backend.cli.provider_setup`; website ingestion → `backend.pipelines.website.ingest`.

## Frontend commands

Run in `frontend`: `npm ci`, `npm run dev`, `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm run preview`. Build includes type checking.

## Safe search verification

`python -m evaluation.search_smoke --input evaluation/search_cases.json --output-dir outputs/search_smoke` runs locally without API startup, provider calls, index updates or automatic model downloads. Exit 0 means every check passed; exit 1 means a result/prerequisite failure.

## Historical evidence

`python -m scripts.verify_submission --portable` verifies archived artifacts without model calls. The scenario runner can generate new LLM assessments; do not invoke its default execution for offline verification. Existing final answers are historical and have documented content limitations.

Set `PROVIDER_PROBE_ON_STARTUP=false` for API startup without live provider probes. Assessment and ingestion actions still make their documented model calls.

Provider routing occurs on demand during model-powered actions. Set `PROVIDER_PROBE_ON_STARTUP=true` only to enable a live startup check.

## Dependency audit

`npm audit --omit=dev` reports no runtime dependency advisories at this update. The full audit reports seven moderate development-tool advisories inherited through ESLint/minimatch; npm reports no compatible fix. Do not force a major minimatch override: ESLint depends on its older API. Recheck before updating lint tooling.
