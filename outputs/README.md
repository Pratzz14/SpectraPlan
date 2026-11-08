# Local outputs

SpectraPlan writes generated diagnostics, evaluation runs and runtime data here. Git tracks this guide. Back up any local outputs you need to reproduce a result or recover application data.

| Location | Contents |
|---|---|
| `runs/`, `H01.json`–`H06.json`, `run_manifest.json` | Evaluation batches and published local answers. Keep the manifest and its referenced artifacts together. |
| `assessment/explainability.sqlite*` | Private local enquiry and lead history. Back up the database consistently. |
| `embedding_models/` | Reusable model cache for offline semantic search. |
| `pdf_knowledge/`, `ingest/cache/` | Ingestion work and caches used to resume processing. |
| `search_smoke/`, `refactor-tests/` | Rebuildable local check output. |

See [operations](../docs/operations.md) for backups and verification and [quality](../docs/quality.md) for interpretation limits.
