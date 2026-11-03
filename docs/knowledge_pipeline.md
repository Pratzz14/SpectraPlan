# PDF and Office knowledge pipeline

The pipeline supports the five supplied PDFs (S01–S05), `AFS_method_comparison_table.xlsx` (T01), and `AFS_Examples_and_Reference.docx` (D01_DOC). It uses Qwen3.7 Flash with lightweight readability checks, bounded retries, and local text/OCR recovery. Qwen receives PDF page images; Office inputs retain cell and paragraph/table-row references.

The supplied batch covers seven sources, 64 PDF pages and eight Office sections/worksheets (72 source locations). The repaired 2026-11-03 batch contains 308 readable Qwen records, 44 locally recovered passages, and 19 exact workbook rows (371 total). Twenty-seven locations used local recovery and none remained unreadable. DashScope returned HTTP 403 near the end of extraction; the remaining Office content was recovered locally. The active manifest and validation report contain the current record counts and recovery status. Development examples and business context remain available in inspection search. Readability checks do not establish scientific correctness or human review.

## Commands and inputs

Set `DASHSCOPE_API_KEY` and optionally `DASHSCOPE_BASE_URL` in the root `.env` or environment. The default endpoint is the existing Alibaba Singapore workspace. These settings are separate from assessment provider routing.

```powershell
# All supported files; reuse matching completed responses:
.\.venv\Scripts\python.exe -m backend.ingest build --concurrency 4
# Optionally rebuild selected sources while retaining the rest of the library:
.\.venv\Scripts\python.exe -m backend.ingest build --source S04
.\.venv\Scripts\python.exe -m backend.ingest build --refresh
# Local preparation only, no uploads:
.\.venv\Scripts\python.exe -m backend.pipelines.pdf_knowledge.extract --prepare-only
# Publish only a complete latest extraction, without new Qwen calls:
.\.venv\Scripts\python.exe -m backend.ingest publish
.\.venv\Scripts\python.exe -m backend.ingest validate
```

A complete batch has 64 PDF pages, two worksheets, and six Word sections (72 source units). Word sections group paragraphs and table rows without dropping their original locations. Unknown files, the S06 URL, challenge inputs, and separate final-evaluation inputs are not read by this command.

Each PDF page is rendered at 180 DPI and sent to Qwen as a PNG. Embedded PDF text stays local for completeness checks and recovery; it is not added to the model image prompt. Excel sheets are read with formulas and cell coordinates intact; Word body paragraphs and tables are read in document order. Office text is sent to Qwen directly. The workbook importer also preserves all 19 exact method rows, all nine columns, and all seven notes independently of Qwen's summaries. Original Office files are never edited or resaved.

Requests use thinking enabled, a 12,000-token completion budget, a 240-second timeout, and structured JSON output. One to four requests can run concurrently (default two). Each unit has at most three attempts (configurable from one to five). Invalid JSON, incomplete responses, unreadable claims/quotes and transient transport/HTTP failures retry with a short delay; numeric Retry-After is capped at ten seconds. Authentication and permanent HTTP failures skip retries. Exhausted attempts recover local embedded text using PyMuPDF, then try local Tesseract OCR when embedded text is unreadable. Office recovery uses the original section text. Recovery stores source passages, not fabricated claims. Pages still unreadable retain their preview and an explicit warning with no invented record. Actual input/storage failures block publication. There is no automatic provider switch. Rerunning rechecks cached Qwen answers, reuses valid completed units, and retries unreadable units. `--refresh` explicitly replaces completed answers too.

## Knowledge and source previews

Qwen returns claims, supporting text, categories, scope, evidence kind, quantities, relevance, caveats, titles and source limitations. Checks cover complete responses, JSON field types, and readable claims/quotes (at least 20 characters, meaningful alphabetic content and distinct words). Single-letter records such as “A” / “a” are rejected. Empty non-reference answers on substantive source content retry. Office supporting excerpts receive a broad source-token overlap check; PDF image text can include information absent from the embedded text, so it is not rejected on that basis. Unknown categories and quantities that do not match a quote verbatim are retained. No verification-model call, coordinate localization, or scientific acceptance gate is added.

Canonical records use `content_kind=llm_knowledge`, `validation_basis=readability_checks`, and `human_review_status=not_reviewed`. Exact workbook rows use `content_kind=method_row` and `validation_basis=source_cells`. Recovered passages use `content_kind=extracted_text`, `validation_basis=source_text_checks`, and their actual `extraction_method` (`pymupdf_embedded`, `pymupdf_ocr`, or `office_text`). Attempt counts and recovery reasons appear in provenance. Original Qwen output is retained under `knowledge`; code attaches source hashes and `source_unit_id` rather than trusting model-generated references.

In [Extracted knowledge](http://127.0.0.1:5173/#knowledge), choose a source, location, or category, then inspect the record beside its source. PDF previews retain zoom and page-specific original links. Excel previews show cell coordinates/values; Word previews show paragraphs and table rows with locations. Office previews preserve text/data, not native application formatting; use the original-file download for that. Sources with matching physical page numbers have distinct location IDs. Empty source units remain inspectable.

## Search and assessment boundaries

All seven sources appear in inspection and can be searched there. The PDF flyer is business context; the Word document contains development scenarios and worked example answers. Their Qwen records remain explicitly labeled and are excluded from default technical assessment retrieval. Research sources remain research demonstrations. Workbook methods retain their underlying S01 Table 1, physical page 6 citation alongside their actual spreadsheet row.

Technical BM25/Qdrant indexes contain only retrieval-eligible records. A separate `inspection/` index includes the flyer and Word examples. Both use existing local BGE embeddings; query selection does not call Qwen. Index text includes claim, supporting quote, relevance, and caveat. The inspector's semantic search can be restricted to a selected source before ranking.

`POST /api/search` adds `dataset=inspection` and an optional `source_id`. Default `technical`, `website`, and `all` search behavior remains intact; `all` still means technical plus website. Inspection results include context labels and do not become assessment evidence. `GET /api/knowledge/inspection` adds source-unit metadata and Office source content within the existing envelope. Evidence resolution for assessment still excludes contextual records.

`GET /api/knowledge/versions/{version}/source/{source_id}/original` serves only inventoried, hash-matching PDF, XLSX, or DOCX originals. PDF responses are inline; Office files download with their proper type and filename. The older `.pdf` route remains supported. Versioned image/report routes remain allowlisted.

## Organization and publication

The workflow lives in `backend/pipelines/pdf_knowledge/`: input preparation, Qwen extraction, and publication. Assessment, website ingestion, and optional document comparison retain their own packages. Root module aliases preserve existing imports.

`qwen-sources-v2` tracks expected units per source and both index memberships, without requiring verifier approval. The previous `qwen-image-v1` and historical F02 corpus readers remain supported. Publication switches `knowledge/current.json` atomically only after all requested units and both indexes complete. A failed or prepared-only batch leaves the current corpus intact.

`outputs/pdf_knowledge/latest/` contains a single replaceable working set, with fixed per-source input/result files and one manifest. Completed answers are reused only when input/source hashes, prompts, schema, model, endpoint and settings match. The already published S04 answers can be migrated locally when their source, image, prompt and output contents still match. Credentials, model reasoning and raw HTTP error bodies are never saved.

The reusable staging directory is `knowledge/.staging/pdf-knowledge-latest/`. CLI builds use a file lock. Publication retains only the latest Qwen generation, preserving historical pre-Qwen evaluation corpora. Pruned versions return unavailable rather than silently resolving to different records.

## Add a new file from CMD or the UI

From Windows Command Prompt, run:

```cmd
cd /d "C:\Users\prati\OneDrive\Desktop\SpectraPlan"
.venv\Scripts\python.exe -m backend.ingest add --file "C:\path\new-paper.pdf" --role research
```

The same command accepts `.xlsx` and `.docx`. Source types are `technical` (default), `research`, `business`, and `development`. Use `--prepare-only` to register and render/read the file locally without a model call or publication. Configure `DASHSCOPE_API_KEY` in `.env` for Qwen extraction; without it the same command uses local recovery. The live command sends the selected file's page images or Office text to the configured DashScope endpoint.

The command adds the selected file to the active library and rebuilds both search indexes. It sends only that new/updated file to Qwen; existing source records are retained without model calls. Reusing a filename updates that source rather than duplicating its records. Updates to supplied source filenames keep their established source IDs and evidence roles. Registered additions are also included in subsequent default builds.

In **Extracted knowledge**, select **Add a file**, choose a PDF, Excel or Word file, select its source type, and select **Add and extract with Qwen** (or **Add and extract locally** when no key is configured). The UI identifies the destination service before upload, displays progress, then refreshes and selects the new source when publication completes. The default upload cap is 50 MB (`KNOWLEDGE_UPLOAD_MAX_BYTES`). Empty, unsupported, malformed or encrypted files produce an error; the current published corpus is retained on extraction failure.

`POST /api/knowledge/ingest?filename=...&role=...` accepts a streaming `application/octet-stream` body and returns HTTP 202 with the queued job. Oversized files return 413, unsupported request types 415, invalid names/roles 422, and another running ingestion 409. `GET /api/knowledge/ingest/status` reports queued/running/succeeded/failed state and completed/total locations. The API starts a hidden worker process so backend reloads do not terminate extraction. CMD, UI uploads, and full builds share the same file lock. A rejected concurrent command leaves the running manifest intact. Upload workers keep reporting a heartbeat during model waits and local indexing, and completed CLI batches trigger the inspector refresh.

Uploaded originals are copied to immutable locations under the configured source directory; a failed replacement cannot break the original links for the currently published version. `knowledge/added_sources.json` keeps local source registrations. `outputs/pdf_knowledge/import/` retains only the latest import's diagnostics and job state; staged browser uploads are removed when the worker finishes. No browser-side API key or additional provider is required.

## Recovery settings

`KNOWLEDGE_EXTRACTION_ATTEMPTS=3` and `KNOWLEDGE_RETRY_DELAY_S=1` bound model retries. `KNOWLEDGE_OCR_TIMEOUT_S=60` bounds each local OCR subprocess. Install Tesseract language data for scanned PDFs; discovery checks `KNOWLEDGE_OCR_TESSDATA`, `TESSDATA_PREFIX`, the Tesseract executable directory and standard installation locations. `KNOWLEDGE_OCR_LANGUAGE=eng` selects traineddata (multiple languages use `eng+deu`). OCR uses PyMuPDF at 200 DPI and runs locally. Missing language data or an OCR failure is visible on the source page. The UI, CMD ingestion and full builds share these checks and recovery behavior.
