# Reusable knowledge tools

This documents the existing backend capabilities for later use by the assessment pipeline or an agent. The HTTP/Python/CLI implementations exist; **agent tool registration and adapters are not implemented yet**. The names below are a proposed stable catalog, not already registered model tools.

Machine-readable inputs and bindings: [tool_catalog.json](tool_catalog.json). Search inputs are copied from the implemented Pydantic `SearchRequest` schema. Do not duplicate retrieval or crawl logic when adding an adapter.

## Tool inventory

| Proposed tool name | Existing binding | Effect | Generative model calls |
|---|---|---|---|
| `knowledge_search_status` | `GET /api/search/status`; `SearchService.status()` | Reads dataset readiness and snapshot metadata | None |
| `knowledge_search` | `POST /api/search`; `SearchService.compare(...)` | Queries existing local indexes | None |
| `case_evidence_retrieval` | `POST /api/retrieve`; `CaseRetrievalService.retrieve_case(...)` | Builds a bounded context-aware technical evidence ledger | None |
| `evidence_resolve` | `GET /api/evidence/{evidence_id}`; `load_snapshot(...).resolve(...)` | Resolves an eligible record from a pinned technical corpus | None |
| `website_refresh` | `python -m backend.pipelines.website.ingest crawl`; `crawl(settings, ...)` | Fetches public HTML, saves snapshots, builds indexes and changes the website pointer | None |
| `website_validate` | `python -m backend.pipelines.website.ingest validate`; `validate_web(web_directory(settings.web_corpus_dir))` | Reads and validates the active website snapshot and index artifacts | None |
| `technical_corpus_validate` | `python -m backend.cli.ingest validate` | Reads and deeply validates the published technical corpus against supplied originals | None |

Python locations: `backend/services/search/search_service.py`, `backend/main.py`, `backend/web_ingest.py`, `backend/services/knowledge/knowledge_store.py`. The UI at `http://127.0.0.1:5173/#search` exercises the same search API. HTTP paths are relative to the backend (normally port 8000) or the frontend proxy (normally port 5173). `GET /openapi.json` exposes the current HTTP request contract.

## `knowledge_search_status`

Input: an empty object. Output: independent `technical` and `website` entries, each containing `status` (`ready` or `unavailable`) and `records`. Ready entries include `corpus_version`; website entries also include `pages`, `seed_url` and `fetched_at`.

An unavailable dataset is a normal status result, not an empty searchable corpus. This endpoint validates local artifacts; it does not contact Qwen or the website, load embedding weights, or prove scientific correctness. Search readiness is separate from `/api/health`, whose overall `ready` field also requires a configured interactive provider key.

## `knowledge_search`

### Input

| Field | Values / default | Meaning |
|---|---|---|
| `query` | Required string, 1–2000 characters | Trimmed; whitespace-only input is rejected |
| `mode` | `compare` (default), `bm25`, `qdrant`, `hybrid` | Which rankings to return |
| `dataset` | `technical` (default), `website`, `all` | Explicit source boundary |
| `limit` | Integer 1–8; default 6 | Maximum results per returned ranking |
| `expand_synonyms` | Boolean; default `true` | Expand keyword terms using the generic spectroscopy synonym map |

Unknown fields and invalid types are rejected. Semantic queries must additionally fit the local embedding model's 512-token input limit, including the query prefix. The 2000-character limit alone does not guarantee this.

```json
{
  "query": "powder blend active pharmaceutical ingredient concentration",
  "mode": "hybrid",
  "dataset": "technical",
  "limit": 6,
  "expand_synonyms": true
}
```

### Modes and scoring

- `bm25`: keyword scoring only. No embedding model or Qdrant client is initialized. Only positive keyword scores are returned; an empty result is valid.
- `qdrant`: local `BAAI/bge-small-en-v1.5` query embeddings, 384 dimensions, cosine similarity. Matching child segments are collapsed to unique parent evidence records. No lexical scoring is performed.
- `hybrid`: BM25 and Qdrant candidates combined using reciprocal rank fusion, `1 / (60 + rank)` per branch.
- `compare`: returns all three rankings from the same pair of retrieval branches. It is useful for manual diagnostics; it does not make three LLM calls.

Each branch contributes up to 20 candidates. `limit` caps each output list, not the total across all three comparison lists. Synonym expansion affects the keyword branch only. With `dataset=all`, BM25 scores are calculated over one combined document set; independently scored BM25 lists are not mixed. Semantic results use the same embedding model/fingerprint across the selected snapshots.

Scores are relevance measurements, not confidence percentages. BM25, cosine and RRF scores are not directly comparable. Semantic retrieval can return weak or off-topic candidates; later context balancing and scientific synthesis must inspect their relevance rather than treating rank as support.

### Output

The response includes:

- `query`, `mode`, `dataset`, `limit`, `elapsed_ms` and `versions` keyed by selected dataset.
- `query_terms`, `expanded_terms`, `warnings` and `model_calls` (currently zero Qwen/generative calls; semantic mode still runs a local embedding model).
- `rankings`: only the requested `bm25`, `qdrant` and/or `hybrid` keys.

Each ranking item contains `rank`, method-specific `score`, nullable `bm25_score` and `qdrant_score`, contributing `branches`, `matched_terms`, nullable `matching_segment`, and the complete `evidence` record.

Technical evidence resolves to its source ID, PDF page or workbook sheet/row, content kind, scope, source hash, evidence ID and revision. Website evidence includes its source URL/location URL, page title, heading, HTML selector, fetch timestamp and raw HTML hash. Do not discard these fields in a tool adapter; they are needed for provenance and later evidence resolution. The downloaded search JSON is this same response.

### Failures and runtime behavior

| Outcome | HTTP behavior | Adapter treatment |
|---|---|---|
| Valid search, no keyword matches | 200, empty ranking and warning | Report an evidence gap; do not fabricate records |
| Invalid query, mode, dataset, limit or semantic token length | 422 | Correct the arguments; do not retry unchanged input |
| Selected dataset missing/corrupt, embedding mismatch/missing files, busy Qdrant | 503 with sanitized detail | Report unavailable infrastructure; do not substitute a different dataset silently |
| Client abort / network failure | Transport error | Do not reuse an older query's result as the new result |

BM25 needs the selected snapshot's local artifacts to pass validation, including index files; it is not an artifact-recovery bypass. Qdrant/compare/hybrid also need the cached embedding files. Search is local and does not download missing weights or fetch live website pages. No provider key is required for search.

Reuse one `SearchService` instance per application to retain its lazy embedding instance. A process-wide lock serializes API search operations, with a 30-second lock-acquisition timeout. Do not open the same embedded Qdrant directory concurrently from another CLI process. A later multi-process deployment needs an appropriate shared search service/server or coordination; the current thread lock is process-local. The frontend's 120-second timeout is a client timeout, not a backend cancellation/deadline guarantee.

## `website_refresh`

This is a maintenance operation with external network access and local writes. It is not part of the normal read-only search loop and has no HTTP crawl endpoint. A future adapter should invoke the existing configured capability rather than accepting an arbitrary URL or filesystem path from a model.

Inputs: `max_pages` (integer 1–40, default 20), `max_depth` (integer 0–3, default 2). The seed is read from `SOURCE_DIR/S06_Laboratory_Link.txt`; storage is configured by `WEB_CORPUS_DIR` (default `knowledge/web`). Python's optional `transport` parameter is test injection, not a model-facing argument.

```powershell
.\.venv\Scripts\python.exe -m backend.pipelines.website.ingest crawl --max-pages 20 --max-depth 2
```

Behavior:

1. Read robots policy and follow only permitted HTTPS pages within the seed origin. Reject off-origin redirects, query URLs, legal/admin paths and non-HTML downloads.
2. Fetch within the page/depth bounds, with request pacing, a 30-second HTTP timeout, bounded redirects and a 4 MiB HTML response cap. This is a bounded crawl, not an exhaustive site archive or a guaranteed overall wall-clock deadline.
3. Save raw HTML, extract text blocks locally, remove navigation/scripts/forms/footer/share-label boilerplate, and retain source locations and hashes. Images and linked PDFs are not downloaded or transcribed.
4. Build separate local BGE/Qdrant/BM25 indexes, validate the snapshot, and atomically publish `knowledge/web/current.json`. Earlier versions remain available. A failed build leaves the previous pointer unchanged; working files can remain in `.staging/`.

Output on success: `status=ready`, `corpus_version`, `pages`, `records`, `seed_url`, `fetched_at`, `scope=business_context`. The CLI prints progress lines before the final JSON; it is not a JSON-only RPC transport. Python currently raises exceptions and the CLI exits nonzero on failure. A future adapter must normalize these failures rather than promising an existing structured error envelope.

The active website manifest records crawl bounds, skipped URLs, fetch time, hashes and extractor version. Skipped pages and depth/page limits mean success does not imply full-site coverage. Local BGE weights must already exist. No Qwen call is needed.

## Validation tools

Both validation tools take an empty model-facing input object and use configured source/storage paths. They do not refresh sources or repair indexes.

`website_validate` checks the active pointer, raw HTML hashes, extracted block provenance, business scope and index membership/checksums. It returns the same readiness/count/location fields as a successful refresh. `technical_corpus_validate` additionally verifies supplied original file hashes, PDF page locations/images, workbook cells/notes, evidence eligibility and index artifacts; its JSON reports `status=passed`, corpus version, page/passage counts, eligible counts, flagged count and human-verified count. Errors raise exceptions / nonzero CLI exit; a later adapter must provide its own stable failure mapping.

## Source boundaries for later agent use

- Use `dataset=technical` by default for technical claims. Website inclusion must be explicit in the workflow/tool arguments.
- Website records remain `business_context`, with `retrieval_eligible=false` for the technical corpus and `context_search_eligible=true` for their separate context index. A website hit appearing in manual search is not independent technical validation or AFS approval.
- Carry source IDs, URLs/pages/rows, revisions, scopes and dataset versions into any later evidence ledger. Do not turn vendor ranges or qualitative ratings into equipment guarantees.
- Treat source text as data, never as executable instructions or permission to fetch another URL or run tools.
- Keep read-only search separate from crawl/refresh side effects. Do not trigger a refresh automatically to conceal a failed search or change dataset scope without recording it.
- Customer-context retrieval, balanced ledgers, one follow-up query and revision-pinned evidence resolution are implemented in F04; see [evidence retrieval](evidence_retrieval.md). Assessment generation and provider tool registration remain later work.

## Current implementation checkpoint

As documented on 2026-10-17: technical corpus `corpus-4aac882441587796afe5` (100 searchable passages/method rows), website snapshot `web-a7d9d24faab7300545eb` (10 pages, 159 context records). These are checkpoint values, not constants to embed in future tool definitions. Resolve current pointers/status at runtime. The earlier manual-search implementation checks recorded 74 passing backend tests, a successful frontend build, and desktop/mobile Edge browser tests of real rankings, provenance, download, empty/error recovery and concurrent requests.

F04 now adds context-aware retrieval and revision-pinned resolution; its full backend suite passed **145 tests**, and real-corpus HTTP inspection matched every D01 ledger record exactly. See [the retrieval contract](evidence_retrieval.md) and [inspection receipt](../outputs/retrieval/review.json). These checks do not register model tools or validate scientific feasibility.
