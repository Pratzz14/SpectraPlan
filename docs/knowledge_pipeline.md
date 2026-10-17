# F02 knowledge pipeline

F02 builds source-grounded spectroscopy evidence from the supplied local files. Qwen extraction and verification support Groq and LLMTech with provider-specific credentials, request fields and pacing. Text embeddings and Qdrant run locally. There is no mandatory approval step and no claim of AFS approval.

## Inputs and boundaries

`SOURCE_DIR` defaults to `knowledge/original_sources` and resolves relative to the repository root. The inventory maps the five named PDFs to S01–S05 (19, 20, 17, 6 and 2 pages respectively), the supplied link file to S06, the workbook to T01 and the examples document to a development-only identifier. Actual hashes and counts are calculated from bytes rather than assumed. Unknown files, challenge instructions, examples and evaluation inputs are excluded from technical retrieval. S05/S06 remain business context; S06's website is not fetched.

All 19 method/geometry rows are imported from `method_comparison!A2:I20`, with all nine cell values and `notes!A1:A7`. Workbook rows retain both T01 sheet/row provenance and the underlying S01 Table 1, physical PDF page 6 citation. Ratings remain qualitative. `optical_path_or_depth` is not a remote fiber-link length. The original asterisk and workbook notes are preserved.

## Stages and prompts

1. **Inventory.** Calculate SHA-256, sizes, source roles, actual PDF page counts and workbook dimensions. Require the supplied technical PDFs, flyer and workbook; report missing optional brief/evaluation files without ingesting them.
2. **Page extraction.** PyMuPDF extracts ordered text blocks, raw text, bounding boxes and physical 1-based pages. Render every page to a JPEG for inspection. Send images to Qwen for all slides/flyer pages and pages with significant images or many vector drawings; other pages use extracted text. Text verification does not resend images. Visual verification includes the source page image.
3. **Qwen extraction.** `backend/prompts/knowledge_extract.txt` and strict `PageExtraction` JSON Schema request source block IDs and optional figure transcriptions. Code copies exact block text. Up to four coherent text groups and four separate figure regions are returned per page. Structured facts are selective annotations, not a replacement for the retained source passage. At most one fact per group and three explicitly anchored numerical quantities are allowed. A substantive page cannot silently become an unexplained empty extraction.
4. **Source verification.** `backend/prompts/knowledge_verify.txt` and strict `PageVerification` request one short verdict per candidate. Check every selected text span, fact quote, quantity value/unit and visual region. Permit PDF whitespace differences in fact quotations, retaining the actual source substring; never normalize scientific values or units. Ambiguous, unsupported, unreadable and malformed candidates are held out of retrieval.
5. **Canonical records.** Save exact text, facts, source spans, region, content kind, evidence scope, revision, issues and automated verdict. Default human status to `not_reviewed`. Business evidence remains excluded even if faithfully extracted.
6. **Inspection report.** Produce searchable `review.html` with record filters, all workbook notes, source inventory, page coverage, raw record details and source page previews. Text blocks and visual regions are highlighted. All source content is escaped or inserted as text, including material that resembles HTML or scripts.
7. **Indexes.** Embed eligible evidence locally using `BAAI/bge-small-en-v1.5` via FastEmbed. Use 384-dimensional vectors and cosine similarity in persistent local Qdrant. Build BM25 over the same evidence IDs, including method rows. Split embedding children at sentence/paragraph boundaries, preserving parent evidence IDs. Count actual tokenizer inputs, including headings, and fail instead of truncating an overlength indivisible sentence.
8. **Publication.** Validate source locations, source/artifact hashes, quotations, method cells, notes, membership and index versions. Atomically publish a version pointer only after all required page jobs, report and index stages succeed. Keep earlier generations after any failure.

Qwen source content is processed as evidence, never executed as instructions. General-method evidence, application examples, research demonstrations and business context retain distinct scopes. Research never becomes clinical readiness; qualitative comparisons never become equipment guarantees. Figure text remains machine-transcribed until independently checked by a person. A second model check does not establish scientific accuracy.

## Rate limits and reproducibility

The earlier Groq account reported Qwen limits of 30 requests/minute, 1,000 requests/day, 8,000 tokens/minute and 200,000 tokens/day; rejection messages distinguished 7,000 input TPM and 1,000 output TPM. Groq ingestion defaults to compact block references, `reasoning_effort="none"`, `INGEST_MAX_OUTPUT_TOKENS=1000`, sequential page processing and usage-based pacing. These are Groq defaults, not the settings of the published LLMTech build. The LLMTech override uses the larger budgets and two concurrent page jobs described below. The F01 interactive configuration remains unchanged.

Transient provider retries retain their shared per-request deadline. Ingestion may additionally wait 60 seconds for token refill, with bounded attempts. An explicit single retry is allowed for provider `json_validate_failed`; it repeats the request without repairing content. Daily-budget and authentication failures stop further live requests in the build. Failed pages remain incomplete and cannot cause publication. Increase the output ceiling only when the account supports it. Larger limits are not required to run local validators or inspect existing artifacts.

Extraction and completed verification are cached separately. Fingerprints include source bytes, page blocks, image bytes, prompt/schema versions, extractor version, model, endpoint and request settings. A change to verification can reuse a source-matched extraction response that validates against the current extraction contract, with its original provenance retained. Prompt changes during a build are rejected. `--refresh` bypasses model-stage caches; unchanged cached inputs preserve IDs and revisions. Record content revisions are independent of the corpus aggregate version.

Evidence IDs derive from source, page, source spans, content kind and content identity. Method IDs derive from T01 sheet/row. Qdrant child IDs are deterministic UUIDs. Model artifact checksums and relevant package versions are saved in `index_manifest.json`.

## Artifacts and interfaces

| Artifact | Contract |
|---|---|
| `knowledge/source_manifest.json` | Convenience export of source inventory, pipeline fingerprint, coverage, version and artifact hashes |
| `knowledge/passages.jsonl` | Convenience export of passages and figure transcriptions, including flagged/excluded candidates |
| `knowledge/methods.json` | All 19 method records and original cells |
| `knowledge/method_notes.json` | All seven notes with row numbers |
| `knowledge/validation_report.json` | Published version's validation summary |
| `knowledge/current.json` | Atomic pointer to the active immutable generation |
| `knowledge/versions/<version>/` | Authoritative generation, report, page images, raw extraction, segments, lexical index, vector index and metadata |
| `knowledge/.staging/<run>/` | Unpublished work, status and sanitized failures; failed builds get an inspection report when page processing finishes |
| `outputs/ingest/cache/` | Resumable extraction/verification responses |
| `outputs/embedding_models/` | Local model/tokenizer binaries |

Every record has `validation_status`, `human_review_status` and `retrieval_eligible`. Active records must pass automated source checks, have a supported automated verdict when model-extracted, resolve to an eligible technical source and have no blocking issues. Method rows use exact workbook-cell validation. The service does not automatically set human review to verified.

`GET /api/health` now returns `eligible_passages`, `eligible_methods`, `flagged_records` and `human_verified_records`, replacing approved-record counts. It checks local data/index prerequisites without contacting Groq. Old F01-only corpus fixtures are intentionally not compatible with the stronger F02 publication contract.

`GET /api/knowledge/report` redirects to the current version's inspection report. Versioned artifact URLs expose only that report and allowlisted page images. They do not expose arbitrary files, the source folder, credentials or internal model caches. The UI includes the report link only after corpus readiness succeeds.

`backend.retrieval.search(root, embedding_cache, query, limit=8)` returns the corpus version, query and ranked evidence with branch provenance and RRF scores. It combines up to 20 lexical and 20 dense matches, deduplicating to at most eight parent records. RRF is `1/(60+rank)` per branch. Domain synonyms are generic spectroscopy vocabulary, independent of D/H scenario IDs. Scores are rankings, not scientific confidence.

## Commands and manual verification

### Optional LLMTech compatibility trial

`python -m backend.smoke_llmtech --public-trial` tests synthetic text, a generated diagram, the actual ingestion schema and separate verification schema. It retrieves the public trial credential from the provider's documentation at runtime, keeps it in memory and writes no key to artifacts. No AFS documents are read or sent; production configuration is unchanged. A backend `LLMTECH_API_KEY` environment variable can be used instead of the public trial.

On 2026-10-17 the LLMTech endpoint returned successful strict-schema text and image responses for `nvidia/Qwen3.8-27B-NVFP4`, accepting a 4096-token completion budget. Both synthetic diagram ranges were transcribed. The output also misclassified nonnumerical text as quantities and the model verifier missed it; these issues are explicitly retained in the smoke record. Compatibility success is not full ingestion acceptance. The initial synthetic text test generalized powder to solid; clarified form-preservation wording corrected that in a separate recorded run.

LLMTech documents an API shutdown on 31 October 2026 and invalidation of keys on 1 November, so it is only a temporary provider option. Its shared public trial has an IP-shared prompt cache. See [LLMTech documentation](https://llmtech.eu/docs/). The user explicitly authorized running supplied AFS content through this provider. The ingestion override uses `nvidia/Qwen3.8-27B-NVFP4`, an 8192-token extraction ceiling, up to 2048 verification tokens, two concurrent page jobs and `chat_template_kwargs.enable_thinking=false`. Groq-specific reasoning fields and TPM delays are omitted. HTTP 402 stops the build immediately; transient 429 failures receive bounded retries. The trial credential is fetched from the official documentation into memory and never saved. Existing Groq credentials and the interactive app configuration are preserved.

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m backend.ingest pilot
.\.venv\Scripts\python.exe -m backend.ingest build
.\.venv\Scripts\python.exe -m backend.ingest pilot --provider llmtech --public-trial
.\.venv\Scripts\python.exe -m backend.ingest build --provider llmtech --public-trial
.\.venv\Scripts\python.exe -m backend.ingest validate
.\.venv\Scripts\python.exe -m backend.ingest report
.\.venv\Scripts\python.exe -m backend.ingest search --query "powder blend API concentration"
.\.venv\Scripts\python.exe -m backend.ingest search --query "opaque dairy fat protein"
```

The pilot processes S01 p.10 and S02 p.6 and prints an unpublished report path. Full `build` resumes valid cached stages; `build --refresh` reruns model stages. For a private LLMTech key set `LLMTECH_API_KEY` and omit `--public-trial`. `--provider llmtech` sets provider/model/endpoint/budgets for that ingestion command only. `validate` additionally compares supplied file hashes and workbook cells with the active snapshot. `report` prints the existing report path without changing the immutable generation.

Open the application's **Inspect extracted knowledge** link or the printed local report. Filter by source/page or search a method, quantity or evidence ID. Compare each passage/figure with the adjacent image and highlighted location, inspect flags and complete record JSON, and inspect original table notes. No approval action is required.

## Validation evidence

Automated tests use synthetic fixtures and mocked providers: source boundaries, page numbering, all method rows and notes, exact/whitespace-preserving anchors, quantities, review independence, cache reuse, verdict completeness, checksum failures, index membership, token limits, publication and safe report/API handling. They do not prove real-source extraction quality.

`outputs/ingest/local_retrieval_validation.json` records the earlier local BGE/Qdrant/BM25 component run on synthetic evidence. `outputs/ingest/frontend_qa.json` records earlier browser readiness checks. Those receipts do not by themselves prove real-source extraction quality; the complete live-source result is recorded below. The earlier pilot and interrupted checkpoint files remain unchanged as historical evidence.

### Published F02 result (2026-10-17)

The live-source gate has now passed for `corpus-4aac882441587796afe5`. All 64 source pages are processed, with 152 passages, 81 eligible passages, all 19 method rows and seven notes, 111 embedding segments, 63 flagged records and zero human-verified records. Deep validation and representative real hybrid searches pass. An audit replay of all 64 cached extraction/verification responses reproduces the published records exactly without model calls. See `outputs/ingest/published_validation.json` and the current section of the implementation plan.

The saved 64-page checkpoint and earlier Groq pilot receipts remain historical records. Their incomplete counts do not describe the active generation. Publication validates the defined source and index contracts; it does not establish arbitrary scientific claims or AFS approval. Context-aware evidence balancing and the evidence API remain F04 work.

Published evidence, manifests, lexical data and embedding segments are committed. Originals, model binaries, Qdrant binaries, source images, raw pages and HTML reports remain local and ignored. A fresh checkout must rebuild from the supplied originals before validation, readiness or search can succeed. Do not run concurrent queries against the same embedded Qdrant directory.
