# Context-aware evidence retrieval

F04 turns F03 `CaseFacts` into a bounded technical evidence ledger using the published local corpus. It does not generate an assessment or confirm scientific feasibility. The existing manual search workbench remains available for comparing raw rankings.

## Interfaces

`POST /api/retrieve` accepts the exact `CaseFacts` object returned by `/api/extract`, without a surrounding `facts` property. Retrieval needs no provider key. Duplicate context IDs and references to unknown contexts return 422. Empty or underspecified contexts return successful empty results with explicit gaps, provided the corpus is healthy.

```python
from backend.core.config import Settings
from backend.schemas.models import CaseFacts
from backend.services.search.retrieval import CaseRetrievalService

service = CaseRetrievalService(Settings())
facts = CaseFacts.model_validate(saved_extraction["facts"])
result = service.retrieve_case(facts)
```

Keep the service instance to reuse its local embedding model. A caller can pass an absolute `time.monotonic()` deadline; retrieval uses the earlier of this deadline and `REQUEST_DEADLINE_S` (default 90 seconds).

`RetrievalResult` includes `status="ok"`, corpus/retrieval versions, the semantic threshold, `max_records=8`, `search_rounds`, `evidence`, `queries`, `coverage`, `gaps`, `warnings`, and `model_calls=0`. OpenAPI exposes the nested models.

- Ledger entries contain resolved evidence, context IDs, facets, matches, their best RRF score, and selection reasons.
- Matches expose query/context IDs, admitting facets, admission (`lexical`, `semantic_only`, `structured`), BM25/cosine scores and branch ranks, RRF score, meaningful matched terms, and matching embedding segment.
- Query traces retain source fields, attributed customer statements, expanded/omitted terms, and admitted/rejected candidate decisions. Structured lookup records its supporting application evidence IDs.
- Coverage is `candidate_found` or `gap` for application, geometry, limitations, and compatibility when hardware or a method is mentioned. It means candidate availability, **not verified claim support**. Gaps distinguish absent evidence, the record budget, missing contexts and insufficient input. Unknown customer values remain unknown.

## Search and selection

1. Validate and pin the active immutable corpus once. Every query and resolved record uses that generation, even if `current.json` changes. Exclude business context, flagged/rejected records, and passages without supported automated source checks. Source-validated `human_review_status="not_reviewed"` records remain eligible under the F02 amendment.
2. Build an initial query per substantive context from target, matrix, explicit phase/appearance, goals, process/shared constraints, attributed statements, and consequential unknowns. IDs never become search terms. Unknown-information boilerplate alone does not create a topic. Query compaction interleaves fields, records omitted terms, and fits 512 embedding tokens including the instruction; it never changes source evidence.
3. Collect up to 20 positive BM25 candidates and 20 distinct dense parent records per query. Reuse local BGE-small-en-v1.5/Qdrant indexes and verify model fingerprints. Collapse dense children before applying the parent limit. Fuse with `1/(60+rank)` per branch.
4. Admit a passage with a positive BM25 score and a meaningful context/synonym term, or cosine similarity at least `RETRIEVAL_SEMANTIC_MIN_SCORE` (default **0.65**). Require a relevant facet. Semantic-only matches stay labeled. This threshold is a project heuristic, not a calibrated probability or an entailment test.
5. Admit method rows through structured lookup, rather than unconstrained semantic or incidental keyword matches. Use requested/source-grounded methods, explicit phase where available, and geometry terms in relevant application evidence. Prefer distinct method families before extra geometries. Preserve original cells, qualitative ratings and notes; rows are comparison guidance, not equipment guarantees.
6. Reserve application evidence across contexts, then a relevant method row per context where available. Fill uncovered applicable facets before additional relevant records, favoring matrix/target matches and method diversity. Break ties by evidence ID. Deduplicate parent IDs and exact duplicate passages on the same source/page, preserving distinct method rows. Target four to eight meaningful records; eight is the total cap, never a minimum.
7. If coverage remains weak, run **one additional query across the entire request**, targeting the first uncovered context/facet in input/facet order. Retain target/matrix/phase and facet terms while dropping incidental process wording. Reselect within the same budget and expose remaining gaps.

The small domain-only synonym map in `backend/services/search/retrieval.py` covers MIR/FTIR/mid-infrared, NIR/near-infrared, ATR/attenuated-total-reflection, API/active-pharmaceutical-ingredient, fluorescence/fluorimetry, moisture/water, fiber/fibre, and reflectance/reflection. These aid discovery; they do not establish instrument or operating-condition equivalence. No scenario IDs or scenario-answer rules appear in the map.

## Evidence resolution and failures

`GET /api/evidence/{evidence_id}?corpus_version=<version>&revision=<revision>` returns the exact eligible record. Each ledger record includes this pinned `evidence_url`. Without a version parameter, manual inspection uses the active corpus; assessment/export callers retain the pinned reference.

Responses preserve source ID, original filename/SHA-256, page, exact text, section, content kind/scope, content revision, validation/review metadata, and span/figure locators. Method rows also include sheet/row, raw cells, underlying S01 Table 1 p.6 citation, and all seven `workbook_notes`. Notes attach to the row without consuming separate ledger slots. A method row's filename/hash identify T01, while its page refers to the underlying S01 citation.

Only validated technical-corpus records resolve; arbitrary disk paths and website records do not. Previous generations remain resolvable after publication of a newer one.

| Outcome | HTTP behavior |
|---|---|
| Healthy search without relevant support | 200, empty ledger and gaps |
| Invalid input/context references | 422 |
| Unknown/excluded evidence or unknown version | 404 |
| Requested content revision differs | 409 |
| Missing/corrupt corpus/index, missing/mismatched embeddings, or contention | 503, sanitized error code/message |
| Shared retrieval deadline expires | 504, `retrieval_timeout` |

The API shares a lock with manual search for embedded Qdrant access. Lock waiting consumes the deadline, up to 30 seconds. Deadline checks surround local operations and prevent another search after expiry. An in-process embedding/index call cannot be forcibly interrupted; a late result is rejected after the operation returns. Separate processes must still avoid concurrent access to the same embedded database. Retrieval never silently switches modes, downloads weights, refreshes sources, or rebuilds indexes.

## Verification

`tests/test_retrieval.py` covers deterministic lexical search, synonyms, query attribution/compaction, semantic thresholds, structured methods, context balancing, deduplication, the record cap, one follow-up, empty results, eligibility, exact resolution, revision pinning, corruption, serialization, deadlines and API errors. The full backend suite also checks existing ingestion, extraction, readiness and manual search.

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp tmp/f04-tests
.\.venv\Scripts\python.exe -m backend.cli.smoke_retrieval
```

The offline smoke runner reads hash-pinned accepted F03 outputs and the existing real corpus. It saves complete diagnostics under `outputs/retrieval/`, makes no provider calls, and includes an unsupported target. Development labels and outputs never enter the runtime retrieval service. The inspection receipt identifies the exact output, relevance checks and limitations. These checks do not establish physical spectroscopy performance or independent human validation.
