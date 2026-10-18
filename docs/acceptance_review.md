# Acceptance review — 2026-10-18

This reviews every item in specification section 14. **Passed** means the stated
scope has evidence; **partial** identifies an observed gap, and **unverified**
means no current evidence. Historical receipts are explicitly historical.
The final cases are organizer-provided scenarios, not an unseen benchmark.

The agreed increment preserves the current answers, verifies reproducibility and
finishes setup documentation. General scientific fixes and new final runs are
outside it. F10.2/demo rehearsal/PPTX work is deferred. F08's quality gate remains
open; completing F09 reproducibility does not resolve those failures.

| Section-14 acceptance item | Status | Evidence and limit |
|---|---|---|
| Fresh installation starts backend/frontend using README | Passed for saved-evidence restoration path | `outputs/setup_verification.json`: new virtual environment and npm installation, 64-page restoration with supplied embedding cache, running backend/frontend on isolated ports and live D01/clarification. Cold model extraction and first embedding download were not retested. |
| Arbitrary natural-language enquiry can be submitted through UI | Passed for recorded development flows | Current setup receipt includes live D01 input and clarification through the UI, alongside earlier F07 receipts; this does not establish quality for arbitrary content. |
| Facts/unknowns separated; no unstated numbers introduced | Partial | UI separation and mechanical provenance pass; `docs/scenario_content_review.md` identifies omissions and semantically wrong field assignments. No universal no-hallucination claim. |
| Multiple streams retain targets/properties; hypotheses attributed | Partial | H02 preserves two streams and typed claim provenance exists; omissions elsewhere prevent a general adequacy claim. |
| Credible method hypothesis or justified insufficient-information answer | Partial | H03/H05 have useful uncertainty conclusions; H01/H06 miss supplied context and cannot be counted as justified successes. |
| Recommendations include geometry, qualified range and page evidence | Partial | Structured fields/references validate mechanically; H02's evidence choice and H04's missing cable rationale remain weak. |
| Citation resolves to actual passage; missing references rejected | Passed mechanically; partial semantically | Manifest/envelope validation authenticates pinned ledgers and source excerpts. No independent expert approval is recorded, and membership does not prove entailment. |
| Ranges/important claims have support; workbook/visual provenance retained | Partial | Exact workbook rows, notes and original PDF citation scope are preserved; visual records are automatically checked. Source relevance/use remains an observed limitation. |
| Priority questions explain the affected decision | Partial | Structured priorities/affected decisions render; H01/H06 ask generic questions despite supplied context. |
| Practical first experiment with samples, reference, independent validation, decision basis | Partial | Fields and development examples exist; interface comparisons and tissue/classification experiments can receive generic or unsuitable boilerplate. |
| No unverified compatibility, calibration accuracy or clinical-readiness assertions | Partial | H03/H04 retain caution, but H01/H06 do not adequately address the customer's premise; no broad safety/accuracy claim follows. |
| D01/D02 compared with worked examples; other development cases smoke-tested | Partial | `docs/scenario_content_review.md` covers D01–D08 and official-example context. The recorded coherent eight-case batch has D08 synthesis failure; later isolated outcomes do not close F08. |
| H01–H06 run through generic frozen app and retained unedited | Passed for reproducibility | `outputs/run_manifest.json`, `outputs/submission_verification.json`, original requests, source snapshot and six matching canonical hashes. No final answer was regenerated or edited in this increment. |
| All six complete under recorded config; identity retained; no case content in runtime | Passed within recorded audit scope | Six HTTP-200 complete envelopes share configuration `a145aa9b24d9c70e01bc6bc3344a75766b47ed7bb5cf88cc24fed4b20b340902`. Literal input/ID checks plus runtime inspection found no lookups; not proof against arbitrary equivalent behavior. Setup-only websocket correction is separately disclosed. |
| JSON export, failures and loading states work | Passed for recorded checks | F07 browser receipts, frontend tests and current setup/browser receipt; matching downloads are verified against the selected envelope. |
| Scientific uncertainty distinguished from runtime failure | Passed mechanically | Complete insufficient-information envelopes remain distinct from incomplete processing with `assessment=null`; this distinction does not make every uncertainty explanation adequate. |
| Live-provider run and browser input-to-export verified; evidence types separate | Passed for current setup flow | `outputs/setup_verification.json` and `outputs/setup_checks/` preserve fresh LLMTech D01/clarification, exact JSON download, embedded evidence, history reopen and both PDFs. Historical and controlled checks remain separately identified. |
| README covers architecture, setup, sources, tools, limitations and demo | Partial against original spec; documentation complete in revised scope | README and `docs/reproducibility.md` cover the implemented system and verification. Demo/PPTX work is explicitly deferred; section 13 remains incomplete. |

## Observed final-case limitations

All six envelopes are complete. Their scientific decisions are insufficient
information for H01/H03/H05/H06 and provisional for H02/H04. These are application
decisions, not quality ratings. The [case review](scenario_content_review.md)
records the substantive differences:

- H01/H06: empty extracted context, skipped retrieval and inadequate answers.
- H02: both streams retained, but weak geometry-specific citation use and comparison design.
- H03: appropriate uncertainty with an incomplete distinction between direct and indirect measurement.
- H04: cautious outcome with missing cable-compatibility justification despite available source material.
- H05: appropriate refusal of an exact configuration, with omitted context and no retrieval.

The [implementation review](retrieval_implementation_review.md) traces these
failures to extraction, retrieval admission and synthesis/evidence use. They are
recorded agent inspections of saved outputs, not independent scientific review.
Targeted diagnostic reruns are preserved separately and do not replace answers.

## Implemented scope and deferred work

The specification's older provider/API examples are historical alternatives. The
implemented primary route is `POST /api/assess`, with typed extraction, local
hybrid retrieval, provider routing, bounded repair and durable rounds. Hybrid
search, persistent case storage, history and PDF exports are implemented despite
appearing in the original post-hackathon list. Expert approval, a verified hardware
catalog, full unit/operating-envelope checks, offline spectral analysis and
structured fact overrides remain deferred. F10.2 is deferred by user request.

Source evidence, automated eligibility and citation membership do not establish
physical accuracy, equipment compatibility, calibration validity or clinical
readiness. External retrieval remains disabled in ordinary assessment; optional
website data is separate business context. No supplied original is newly published.

## Completion interpretation

F09 can close its artifact/reproducibility gate with known scientific failures
disclosed. F10 can close only its revised setup/documentation gate after its
fresh-run checks pass. The full specification and F08 remain incomplete wherever
the table records partial or unverified outcomes. No presentation completion or
independent scientific validation is claimed.
