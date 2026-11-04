# Quality and limitations

SpectraPlan provides **initial assessments and proposed experiments**. Automated checks establish schema, attribution, citation membership and artifact consistency. They do not establish scientific entailment, spectroscopy performance, hardware compatibility, calibration accuracy or clinical readiness. No independent expert validation is recorded.

## Known limitations

- Extraction can omit context or misclassify sample properties. A technically complete result can still miss the customer's question.
- Retrieval admission can discard relevant material; a selected/cited passage may be too weak for the proposed method or geometry.
- Synthesis can choose weak excerpts or generic experiment boilerplate despite useful evidence being available.
- Qwen transcription/readability checks and local OCR are not human verification. Research-demonstration scope stays attached to evidence.
- Email confirmation is disabled for the initial password flow, so lead email addresses are unverified. Password recovery/email delivery, sales stages, distributed storage and public-launch usage controls are not implemented.

Preserve unknowns, evidence scope and processing failures when exporting. Treat method suggestions as hypotheses to test with reference assays, independent validation groups and agreed acceptance criteria.

## Historical results

The retained final batch is `4c14fccd1a3d4eadb672c14de91c142e`, generated on 2026-10-18. All six envelopes completed under its frozen configuration. The following findings describe **saved historical outputs**, not a fresh evaluation of the current code/provider/corpus:

| Case | Recorded limitation |
|---|---|
| H01 | Empty extracted context; retrieval skipped; inadequate answer to supplied information. |
| H02 | Both streams retained, but geometry-specific citation use and comparison design were weak. |
| H03 | Useful uncertainty, with incomplete distinction between direct and indirect measurement. |
| H04 | Cautious conclusion, but missing cable-compatibility justification despite available source material. |
| H05 | Appropriate refusal of an exact configuration, but context omitted and retrieval skipped. |
| H06 | Empty extracted context; retrieval skipped; inadequate response to the customer premise. |

The dated D01–D08 reviews also recorded context splitting, incorrect property assignment, irrelevant research citations, inconsistent method choice and incomplete synthesis. These are observed agent reviews, not expert ratings. Later diagnostic successes do not replace canonical cases or prove those problems resolved.

## Reproducibility

Canonical answers are `outputs/H01.json` through `H06.json`, with `outputs/run_manifest.json` pointing to one immutable batch under `outputs/runs/`. The batch retains requests, evidence, trace JSON, settings and execution snapshots. Original inputs, model identities, prompt/schema hashes and source provenance must stay attributable to that batch.

Run `python scripts/verify_submission.py --portable` to check saved artifact consistency without credentials, original files, live indexes or SQLite. Optional trace PDFs may be absent; portable trace JSON remains required. This check never regenerates answers. A full audit also compares current runtime/input material and may report expected code drift; do not rewrite archived manifests to hide it. Its credential scan checks configured API keys, secret keys/access tokens and selected token formats (including Supabase secrets). This is not a complete secret detector or a Git-history audit.

New scientific claims require a new evaluation of the changed system. Keep final inputs separate from development examples, run the whole final batch, preserve earlier results and avoid splicing selected answers. [Operations](operations.md#diagnostics-and-evaluation) distinguishes offline checks from live execution.

## Documentation history

[documentation_archive.zip](../outputs/documentation_archive.zip) preserves all 20 pre-consolidation documents byte-for-byte, including the original specification, implementation plan, detailed case/retrieval reviews, tool catalog, setup receipts and cleanup inventory. Its `manifest.json` records SHA-256 checksums. Those files explain past decisions; use the four current guides for today's setup and operation.

Existing artifact references to the former `docs/` paths are historical provenance. Their original text is available under the same path inside the archive. Canonical answers, run manifests and source snapshots were not edited by documentation consolidation.
