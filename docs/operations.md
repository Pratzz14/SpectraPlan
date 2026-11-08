# Operations

Run from the repository root. `python` below means `.\.venv\Scripts\python.exe` on Windows. Use `python -m <module> --help` for current flags; old provider-selection commands are obsolete.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/pytest
.\.venv\Scripts\python.exe -m evaluation.search_smoke
Push-Location frontend
npm test
npm run lint
npm run build
Pop-Location
```

Backend tests block external HTTP and use disposable history. Domain tests explicitly inject an admin identity; auth tests use the production app with mocked Supabase responses. Search smoke uses existing local indexes and cached embeddings, with no model calls, downloads or publication. Build includes TypeScript checks. Passing these checks does not validate scientific recommendations.

## Knowledge

Place separately supplied originals under `knowledge/original_sources/`. The supplied inventory is:

| ID | Filename |
|---|---|
| S01 | `S01_Multispectral_Laboratory.pdf` |
| S02 | `S02_AFS_Process_Control_Slides.pdf` |
| S03 | `S03_LED_Kidney_Study_2017.pdf` |
| S04 | `S04_Combi_MIR_Fluorescence_2021.pdf` |
| S05 | `S05_AFS_Flyer.pdf` |
| S06 | `S06_Laboratory_Link.txt` (optional website seed) |
| T01 | `AFS_method_comparison_table.xlsx` |
| D01_DOC | `AFS_Examples_and_Reference.docx` |

Check original hashes against the saved source manifest. Originals and local final-scenario text are excluded from Git; their redistribution rights are separate from the code license.

```powershell
# Restore saved evidence and rebuild images/indexes without extraction-model calls.
# Requires matching originals and a supplied embedding cache when local-only.
python scripts/restore_corpus.py --local-model-only
python -m backend.cli.ingest validate
python -m backend.cli.ingest search --query "powder moisture"
```

Restoration publishes a **new corpus identity** while preserving saved evidence IDs/revisions and old generations. `--from-generation <directory>` selects a specific saved generation. Without `--local-model-only`, embedding files may download. Stop other processes that hold the same Qdrant index before restoration or CLI search.

```powershell
# LIVE: sends source content to DashScope and consumes quota.
python -m backend.cli.ingest build --concurrency 2
python -m backend.cli.ingest build --source S04
python -m backend.cli.ingest add --file "C:\path\source.pdf" --role technical
# LOCAL preparation only; no model call.
python -m backend.cli.ingest add --file "C:\path\source.pdf" --prepare-only
# Reuse completed extraction; publication may require local embeddings.
python -m backend.cli.ingest publish
```

PDF, XLSX and DOCX inputs are supported. Source roles are technical, research, business and development. Admins can also add files through Extracted knowledge. `--refresh` replaces matching cached extraction. Failed extraction uses local text/OCR when possible; unresolved storage/input failures block publication. Inspect active manifests for counts, fallback locations and validation status rather than relying on historical totals.

## Diagnostics and evaluation

| Command | Effect |
|---|---|
| `python -m backend.cli.smoke_retrieval` | Local retrieval inspection requiring separately saved extraction fixtures in `outputs/extraction/`. |
| `python -m backend.cli.smoke_provider` | Live structured-output request. |
| `python -m backend.cli.smoke_extraction` | Live customer-fact extraction. |
| `python -m backend.cli.smoke_assessment --case D01` | Live pipeline diagnostic. Add `--api` to exercise authentication/history. |
| `python -m backend.pipelines.website.ingest crawl` | Optional bounded website HTTP crawl; separate business-context dataset. |
| `python scripts/verify_submission.py --portable` | Offline verification of a separately saved or locally generated final batch. |

API diagnostics need a current `SUPABASE_ACCESS_TOKEN` in the process environment; evaluation needs an admin token for traces. It is not a publishable/secret project key. Tokens are not saved in evaluation configuration. For new batches, run `python -m evaluation.run_evaluation --suite development` or `--suite final`; these make live model calls. `--verify <manifest>` verifies saved results; `--publish <manifest>` deliberately updates canonical answers. Do not publish individual diagnostic reruns as a final batch.

## Storage and backup

With `STORAGE_BACKEND=supabase`, use the cloud export and local worker procedures in [Supabase migration](supabase.md). Do not rerun the initial local import/activation after accepting cloud writes. The following filesystem backup instructions apply to the legacy local backend and pre-cutover snapshots.

Use one backend worker. Preserve source originals, active corpus generations/indexes, website snapshots, added-source registry and SQLite history together. For SQLite, use the backup API or stop the server and include any WAL files. Stop ingestion/search clients before copying active indexes. Do not run corpus publication concurrently with searches.

`outputs/embedding_models/` caches embeddings; `outputs/pdf_knowledge/` stores ingestion work; `tmp/`, frontend build output and test caches are disposable when no process is using them. See the [artifact map](../outputs/README.md) for local data and backup guidance.

Current code differs from archived execution snapshots, so a full historical runtime-drift audit can fail even when portable artifact integrity passes. Keep new verification receipts outside immutable run directories. Read [quality](quality.md) before interpreting saved assessments.
