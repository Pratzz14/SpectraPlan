# Setup and evaluation reproducibility

The retained submission contains six machine-produced final envelopes. It records
what the application ran; it does not establish that all six answers are adequate.
The [content review](scenario_content_review.md) and [acceptance review](acceptance_review.md)
describe the observed failures. Demo/PPTX work is deferred.

## Install and start

Use Python 3.12 and Node 22.12+ in its supported release line. From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
Push-Location frontend
npm ci
Pop-Location
```

Supply a backend key for at least one configured provider before live assessment.
`PROVIDER_NAME=auto` uses Gemini → LLMTech → Groq; pinned `gemini`, `llmtech`,
`groq` and optional `regolo` modes disable switching. A configured Regolo key adds
it as a fallback even when omitted from the default order. Preserve an existing
`.env`. Startup can make synthetic provider probes; health refresh reads cached
availability. Assessment sends enquiry/source content to actual selected providers.

The websocket pin is 16.1.1, matching the inspected working environment and the
Google SDK's requirement. The earlier 17.2 pin failed fresh dependency resolution.
The archived final snapshot remains unchanged; this setup correction is recorded
separately and is not a new final-evaluation configuration.

## Restore the saved evidence

Obtain the originals separately and place them in `knowledge/original_sources/`:

| Source | Filename |
|---|---|
| S01 | `S01_Multispectral_Laboratory.pdf` |
| S02 | `S02_AFS_Process_Control_Slides.pdf` |
| S03 | `S03_LED_Kidney_Study_2017.pdf` |
| S04 | `S04_Combi_MIR_Fluorescence_2021.pdf` |
| S05 | `S05_AFS_Flyer.pdf` |
| S06 | `S06_Laboratory_Link.txt` |
| T01 | `AFS_method_comparison_table.xlsx` |
| Development | `AFS_Examples_and_Reference.docx` |

The source manifest records their required hashes. Originals and the local final
scenario file are ignored; redistribution permission has not been established.
Required stored evaluation inputs and source excerpts retain their original rights.

```powershell
.\.venv\Scripts\python.exe scripts/restore_corpus.py
.\.venv\Scripts\python.exe -m backend.ingest validate
.\.venv\Scripts\python.exe -m backend.ingest search --query "powder blend API concentration"
.\.venv\Scripts\python.exe -m backend.ingest search --query "opaque dairy fat protein"
```

Restoration checks the saved evidence and original file hashes, renders all 64
PDF pages, rebuilds BGE/Qdrant/BM25 and the report, and deeply validates before
switching the active pointer. It preserves passages, evidence revisions, exclusions
and workbook notes. It performs **zero extraction-model calls** and assigns a new
corpus identity because the rebuilt vector database has its own binary hashes.
Old generations and archived final-run evidence remain unchanged. Failed stages
remain under `.staging`; the previous active generation stays selected.

The first BGE use downloads public embedding-model files. An existing matching
`outputs/embedding_models/` cache can be copied for offline restoration. That
cache reuse must be disclosed when reporting fresh-setup evidence. Stop other
clients before accessing the same local Qdrant generation from a separate process.
Use `python scripts/restore_corpus.py --local-model-only` when a matching embedding
cache is already supplied and model-file downloads must be disabled.

To re-extract sources through configured providers instead of restoring saved evidence:

```powershell
.\.venv\Scripts\python.exe -m backend.ingest build --provider auto
.\.venv\Scripts\python.exe -m backend.ingest validate
```

This sends page text/images to providers and can take many calls. Compatible caches
resume completed stages; `--refresh` reruns them. A new build is not the frozen
submission corpus. Extraction, embedding and source scope are explained in the
[pipeline contract](knowledge_pipeline.md). S05 is business context; S03/S04 research
scope remains attached to evidence. The optional S06 website crawl is separate
business context; ordinary assessment performs no external retrieval.

Start the two services in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```powershell
Set-Location frontend
npm run dev
```

Open `http://127.0.0.1:5173`. A missing key/corpus produces explicit readiness or
incomplete-run information; an HTTP-200 health response alone is not readiness.

## Inspect the retained final batch

Batch: `4c14fccd1a3d4eadb672c14de91c142e`, generated on 2026-10-18.
Its source/configuration snapshot includes the dirty implementation state at
revision `d44d6f9244f782f9d67b8470455f58e2f6186692`; the revision alone is insufficient.
Configuration ID: `a145aa9b24d9c70e01bc6bc3344a75766b47ed7bb5cf88cc24fed4b20b340902`.

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --verify outputs/run_manifest.json
.\.venv\Scripts\python.exe scripts/verify_submission.py --portable
```

These checks need the archived run directory and installed application packages,
but no credentials, original source files, live index or history database. Requests
contain only the exact initial `description`: no case ID, history or clarification.
Evidence JSON, trace JSON and full source/configuration snapshots are adjacent
to each run. Canonical H01–H06 files are byte-for-byte copies of that one batch.
Earlier failures and diagnostic reruns are retained; diagnostics are not replacements.
Git attributes preserve these hashed artifacts as exact bytes, including archived
source snapshots, so checkout line-ending conversion cannot invalidate their hashes.
Redundant trace PDF renderings remain local and ignored: some are larger than
100 MB. Their original hashes remain in the unchanged manifests, but they are
optional derivatives rather than portable review dependencies. Complete trace
JSON is retained and required. The verification helper checks PDF hashes when
those files are present and reports local-only derivatives when absent. See
`outputs/archive_storage.json` for the PDF inventory; no answer or trace JSON was removed.

The full audit additionally needs `evaluation/final.json`'s recorded original source
location and the active corpus:

```powershell
.\.venv\Scripts\python.exe scripts/verify_submission.py --receipt outputs/submission_verification.json
```

It compares original inputs, captured execution files, runtime prompts/code and
eligible corpus text, checks a database-free portable copy with HTTP/SQLite disabled,
and scans tracked/nonignored files for configured credentials and selected token
formats. The scan is not a complete secret detector or a Git-history audit. Receipts
are separate from immutable answers and manifests. The known requirements-pin
correction is reported explicitly; other execution-file drift fails this audit.

The frozen automatic order was Gemini → LLMTech → Groq. All twelve successful
stages used LLMTech, requested `nvidia/Qwen3.8-27B-NVFP4`, returned `qwen38`.
Gemini quota failures remain in provider-attempt records. Request/call limits were
180/60 seconds, with 3072 extraction and 4096 synthesis output tokens, bounded
repair and at most eight ledger records. Inspect the frozen configuration for all
remaining settings and actual per-stage attempts. These are organizer-provided
scenarios, not an unseen benchmark. Repeating calls cannot guarantee identical text.

## New evaluation runs

Use a separate workspace if generating new results. Supply the original final
scenario file at `knowledge/original_sources/customer_scenarios_for_final_evaluation.txt`:

```powershell
# D01–D08, same public assessment route, isolated history
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --suite development --provider auto

# New H01–H06 batch; prepare exact source spans and hashes first
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --prepare-final
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --suite final --provider auto --request-deadline-s 180 --call-timeout-s 60
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --verify outputs/runs/<batch>/manifest.json
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --publish outputs/runs/<batch>/manifest.json
```

Final mode runs all six. Freeze effective profiles/settings/corpus before running;
the command alone does not reproduce the archived configuration. Publication
requires completeness and preserves earlier canonical files. Any later general
assessment fix needs a new version and a whole-six rerun; never splice answers.
No final regeneration or scientific tuning is part of this verification increment.

## History, exports and checks

`EXPLAINABILITY_DB_PATH` controls local SQLite history. History reopens an enquiry,
selects a round and continues with attributed clarification answers. JSON preserves
the full selected machine envelope. Chemist PDF is the concise assessment; trace
PDF/JSON include original enquiry, source excerpts, retrieval/model events and
validation content. These are content-bearing exports; review them before sharing.
Evaluation uses isolated history, and portable exports remove any review dependency
on SQLite. Databases stay local and ignored.

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/pytest-fresh
Push-Location frontend
npm test
npm run build
Pop-Location
```

The [setup receipt](../outputs/setup_verification.json) distinguishes fresh
dependency installation, corpus restoration with a supplied embedding cache,
runtime/browser checks and historical live-provider evidence. A cold live-model
source re-extraction is a separate operation, not implied by restoration success.
