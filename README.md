# SpectraPlan

SpectraPlan is a planned AI assistant for the first technical assessment of industrial spectroscopy enquiries. It will help an Art Fiber Systems (AFS) expert identify missing information, compare promising measurement approaches and design an initial feasibility experiment using the supplied AFS materials.

## Project status

The repository currently contains the technical specification and an iterative implementation plan. The application, ingestion pipeline and evaluation runner have not been implemented. Installation and startup commands will be added as those components become available.

## Project documents

| Document | Purpose |
|---|---|
| [Technical specification](docs/plan/spec.md) | Product scope, source handling, data contracts, architecture and acceptance criteria |
| [Implementation plan](docs/plan/implementation_plan.md) | Ten ordered features with task/subtask checklists, dependencies, completion gates and a progress log |

To begin, follow **F01 — Project foundation and provider connection** in the implementation plan. Work through one task or feature at a time, verify its completion gate and record the result before moving on. The proposed MVP budget is 12 hours; it is a project planning choice.

## Planned workflow

1. Enter a customer enquiry in natural language.
2. Extract stated facts, unknowns and distinct process streams while preserving input provenance.
3. Retrieve reviewed AFS passages and method-table evidence.
4. Produce conditional method and measurement concepts, prioritized questions, limitations and a practical first experiment.
5. Inspect claim-level source references and export the generated assessment with its evidence and run metadata.

The assistant supports expert review. Its recommendations are hypotheses to test; the software does not establish measurement accuracy, equipment compatibility or clinical readiness. A justified insufficient-information assessment is a valid result.

## Planned architecture

| Layer | Proposed implementation |
|---|---|
| Interface | React, TypeScript, Vite and Tailwind |
| API and validation | Python 3.11+, FastAPI and Pydantic v2 |
| Document ingestion | PyMuPDF and openpyxl |
| Retrieval | BM25 with local JSON/JSONL evidence and a structured method table |
| Generation | Configurable model provider with structured responses, bounded retries and local validation |

The backend will run extraction, retrieval, synthesis and validation. API credentials will remain on the backend. External retrieval is disabled by default in the MVP design.

## Source materials and evaluation

The supplied AFS PDFs and method comparison workbook are the primary technical references. Source locations must remain traceable to PDF pages, slides or workbook rows. Business materials and research demonstrations retain their original scope.

Organizer-supplied original files are not included in this repository. The planned local location, `knowledge/original_sources/`, is ignored by Git. The implementation will document how to configure source paths and rebuild the reviewed corpus.

Development scenarios **D01–D08** and organizer worked answers are used for development and review, separately from technical retrieval. Final scenarios **H01–H06** must run through the general application pipeline. Their answers must be generated without manual editing or case-specific hardcoding.

Required final artifacts will include `outputs/H01.json` through `outputs/H06.json` and `outputs/run_manifest.json`. These outputs and the reviewed corpus are intentionally not globally ignored by Git. They have not been generated yet.

## Verification

During implementation, record automated checks, source review, live provider runs and browser verification separately in the implementation plan. No application runtime or scientific performance has been validated at this planning stage.

## License

Original SpectraPlan project content is available under the [MIT License](LICENSE).

Third-party AFS materials, research papers and any excerpts or figures derived from them retain their respective rights and are not relicensed by this repository's MIT License.
