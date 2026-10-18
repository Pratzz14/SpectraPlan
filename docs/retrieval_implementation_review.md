# Assessment retrieval implementation review

Reviewed the saved six-case batch `4c14fccd1a3d4eadb672c14de91c142e`,
the public API and assessment orchestration, extraction/recovery, local index
construction, hybrid search, admission, evidence selection, synthesis schema,
validation, and evaluation verification. This is an implementation/content review,
not an independent scientific assessment. No generated answers were edited.

## Finding

The local Qdrant index works and contains relevant supplied material. The
assessment pipeline can bypass search, discard useful search hits, and choose
weak excerpts from the evidence that survives. A completed envelope does not
establish that the enquiry has been answered adequately.

## Actual execution path

1. The evaluation runner posts the original description to `/api/assess`.
2. The API saves history, calls `assess_case`, and records stage/provider events.
3. Extraction creates typed `CaseFacts`; its schema permits empty lists.
4. `CaseRetrievalService` searches from those facts, not the original enquiry.
   With no contexts it returns a missing-context gap without searching.
5. Otherwise it builds queries from fields, statements and missing information.
6. BM25 returns up to 20 evidence records. Qdrant searches local BGE embeddings,
   collapses segment hits to distinct evidence records, and keeps 20 parents.
7. Reciprocal rank fusion combines branches with k=60. Admission applies lexical,
   semantic-threshold and facet gates; structured method-table lookup is separate.
8. Selection creates a ledger of at most eight records. It may stop at four or
   more when remaining records add neither facet coverage nor a new method.
9. Synthesis receives the selected records and facts, not the raw rankings or
   original description. Dynamic schema enums constrain many assertions to
   excerpts from selected records and predefined gap statements.
10. Mechanical validation and exports check consistency and provenance, not
    whether all important customer facts and scientific questions were addressed.

## Saved-run evidence

Counts below distinguish actual hybrid searches from structured method lookups.
Branch counts are ranked occurrences, not distinct files or proof of relevance.

| Case | Contexts | Hybrid searches | BM25 hits | Qdrant hits | Ledger records | Final source references |
|---|---:|---:|---:|---:|---:|---:|
| H01 | 0 | 0 | 0 | 0 | 0 | 0 |
| H02 | 2 | 2 | 40 | 40 | 5 | 1 |
| H03 | 1 | 1 | 20 | 20 | 4 | 0 |
| H04 | 1 | 1 | 20 | 20 | 5 | 2 |
| H05 | 0 | 0 | 0 | 0 | 0 | 0 |
| H06 | 0 | 0 | 0 | 0 | 0 | 0 |

The active corpus is `corpus-4aac882441587796afe5`, with collection
`afs_evidence` in its local `qdrant` directory. Embeddings use
`BAAI/bge-small-en-v1.5`, 384 dimensions and cosine similarity. The assessment
semantic admission threshold is 0.65. Index/corpus and embedding hashes are checked.

## High-priority defects

### Empty extraction is accepted, then prevents retrieval

H01's raw extraction itself contained empty contexts, statements, constraints
and unknowns. Recovery did not remove a populated context. H05 and H06 retained
statements but no contexts. `validate_extraction` checks supplied facts and quote
membership, without checking coverage against substantive original input.
`retrieve_case` returns before loading the embedder or opening Qdrant when
`facts.contexts` is empty. Synthesis then receives no original description from
which to recover the lost facts. It is allowed to return a complete clarification
assessment, producing a misleadingly successful execution result.

Correction: support grounded retrieval from the original enquiry or verified
case-wide statements when contexts are absent; warn about extraction coverage
loss and preserve original input for synthesis. Do not invent analytes or phases
to manufacture a context or confuse unknown composition with no usable enquiry.

### A relevant H04 cable hit is rejected by facet classification

`S02:p007:txt:856fd5ec4ff1cc27` ranked sixth in Qdrant at cosine 0.663379,
above 0.65. It was outside BM25's top 20. Its recorded admission decision is
false with reason `no_relevant_facet`. The text discusses silica fibers, cables,
and Vis-NIR process control, but the hardware classifier tests singular tokens
such as `fiber` and `cable`. Synonyms are expanded for query tokenization, not
consistently for the source-side facet classifier. Its structured fact category
is application, so it does not rescue the missing compatibility facet.

Correction: normalize spelling and inflection consistently on both sides and
explicitly retain hardware compatibility evidence. A relevant source can add
important support or contradictions even when a broad facet is already covered.

### Useful H02 evidence reaches synthesis but is not cited appropriately

The ledger contains S01 page 18, whose text explicitly discusses transmission
for dilute whey and reflection for highly scattering products. Synthesis cites
only page 17 for both recommendations; its quoted rationale concerns reflection.
Method-family validation accepts both as NIR and does not distinguish geometry
or limitation applicability. The experiment assigns one geometry per stream
instead of comparing alternative interfaces within each applicable stream.

Correction: select support at recommendation/geometry level, keep limitations
with their applicable configuration, and make the experiment compare the options
the customer asked to compare. Citation membership alone is insufficient.

## Additional implementation findings

- Recovery puts diagnostic warnings in `facts.missing_information`, and
  `_context_fields` includes that list in the embedding query. H04's actual query
  includes internal words such as extraction, warning, shared_constraints and
  paraphrase. Keep diagnostics out of customer unknowns and search inputs.
- `_compact_query` interleaves and deduplicates word tokens across fields. This
  destroys sentence structure, including associations between properties and
  qualifiers, before dense embedding. Use a concise grounded natural-language
  query, while retaining a separate lexical term representation.
- Selection is based on broad facets, affinity and method diversity, rather
  than explicit question coverage. Its early-stop rule can omit another important
  compatibility or limitation passage even when fewer than eight are selected.
- `_assertion_choices` exposes only bounded sentence excerpts (first eight
  eligible excerpts per record). The dynamic schema can force repetitive,
  irrelevant approved sentences rather than a coherent supported explanation.
  H04 repeats cost as a risk; H06 uses a generic calibration-transfer gap.
- Predefined gap statements are offered regardless of enquiry topic. Constrain
  gaps to the actual missing evidence; separate source claims from reasoned
  uncertainty explanations and proposed experiments.
- `/api/search` and `/api/assess` use different retrieval implementations. The
  search workbench can find material that assessment never queries or rejects.
  Share the underlying engine or explicitly test and document those differences.
- Verification leaves semantic source support unreviewed. A passed manifest is
  an artifact-integrity result; extraction coverage and answer adequacy need
  separate reported quality checks without suppressing usable partial answers.

## Local diagnostic on original enquiries

Ran the existing SearchService locally in compare mode against the original
H01 and H06 descriptions, without external provider calls or altered inputs.
This diagnostic is separate from their preserved assessment runs.

- H01: top Qdrant hit S01 page 15, `S01:p015:txt:5d65dd1642425d18`,
  cosine 0.8019. Top hybrid hit was the same passage; BM25 ranked page 14 first.
- H06: top Qdrant hit S03 page 14, `S03:p014:txt:a259419b88f6c155`,
  cosine 0.8368. Top hybrid hit was S03 page 2,
  `S03:p002:txt:fcebfbe576cee0fa`; BM25 also ranked that passage first.
- The active S03 corpus has 36 records, 18 marked retrieval-eligible.

These results demonstrate index availability and retrieval plausibility, not
scientific entailment. The issue is the assessment route's orchestration and
selection, not an absence of relevant files in Qdrant.
