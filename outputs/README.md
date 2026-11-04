# Artifact map

This folder contains both retained evidence and local working files. Do not delete it as a generic build folder.

| Location | Treatment |
|---|---|
| `H01.json`–`H06.json`, `run_manifest.json` | Canonical historical final batch; preserve exact bytes. |
| `runs/` | Frozen batches, requests, answers, evidence, traces and execution snapshots; preserve referenced artifacts. |
| `diagnostics/`, tracked development/provider/extraction/retrieval outputs | Historical evidence; preserve referenced records. |
| `documentation_archive.zip` | Original documents before consolidation, with a checksum manifest. |
| `archive_storage.json`, verification receipts, `setup_checks/` | Historical provenance and checks; not claims of current scientific adequacy. |
| `assessment/explainability.sqlite*` | Private local enquiries/leads and WAL files; ignored by Git. Back up consistently. |
| `embedding_models/` | Reusable model cache; needed for offline semantic search. |
| `pdf_knowledge/`, `ingest/cache/` | Ingestion work/cache; retain when resumability matters. |
| `search_smoke/`, `refactor-tests/` | Rebuildable local check output; ignored by Git. |

Historical paths in saved reports refer to the code/docs that existed at execution time. Old documentation lives inside the archive with those original names. The canonical run directory is selected by `run_manifest.json`; folder age alone is not a deletion rule.

Use [operations](../docs/operations.md) for backup, restoration and verification, and [quality](../docs/quality.md) for interpretation limits.
