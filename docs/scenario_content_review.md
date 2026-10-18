# D01-D08 and H01-H06 content review

## Scope and evidence

All 14 stored enquiries were checked with the implemented source-verification
loaders. Development text matches the supplied `AFS_Examples_and_Reference.docx`
paragraphs and SHA-256; final text matches the supplied final-scenario file,
source spans and SHA-256. No input was reconstructed or edited for this review.

Development answers below refer to the latest saved batch that attempted all
eight cases: `outputs/development/20261018T104630Z_13bffba3ae73447982827b5f96da41d9`.
It used assessment-v5, so its findings are historical evidence, not a claim about
a fresh run of assessment-v7. The latest separate D08 attempt at 10:50 also
failed synthesis. An older D08 success at 10:32 is discussed explicitly as older.

Final answers refer to the canonical six-case batch
`outputs/runs/20261018T143757Z_4c14fccd1a3d4eadb672c14de91c142e` (assessment-v7).
The targeted H01/H05/H06 reruns in
`outputs/diagnostics/recheck_20261018T145852Z_2ac75ad2` are additional observations,
not replacements for individual members of that final batch.

This review inspected saved output content, extracted facts, selected evidence
identities, recommendation rationales and experiment plans. It is not an
independent scientific validation or a fresh 14-case provider run.

## Development enquiries

| Case | What the enquiry requires | Observed result |
|---|---|---|
| D01 | API in powder at a tablet feed frame; compare measurement options against existing lab checks. | Partial. Powder/API/lab checks retained, but a probe/location is split into a second measurement context. Only NIR is evaluated, despite the request to compare reasonable options. The extraneous context adds irrelevant characterization questions. |
| D02 | Opaque concentrated dairy; fat/protein; temperature and texture variation; retain lab checks. | Relatively useful. NIR reflection and paired references address the main request. Typed extraction incorrectly labels `opaque` as sample phase and `concentrated` as concentration range. The comparison is primarily one optical method versus reference assays, rather than a developed interface comparison. |
| D03 | Whey/protein monitoring that remains useful as turbidity changes. | Partial. Turbidity is represented in the experiment, but protein is omitted from typed analytes. The NIR/transflection and Raman rationale is a broad statement about additional dairy techniques rather than support for the exact proposed geometries under changing turbidity. |
| D04 | In-situ glucose/lactate pilot in changing cell-culture medium, checked against existing assays. | Unsupported rationale. Recommends NIR using the kidney-study sentence `The NIR spectra of the Series A samples are presented in Figure 5a.` This does not establish cell-culture/analyte suitability. The tentative experiment is more relevant than its supporting citation. |
| D05 | Separate biomass from metabolic signals in yeast fermentation; define targets/references and handle rising optical density. | Unsupported and premature. Recommends NIR and Raman cuvettes while citing tumor-boundary material. Biomass/metabolic targets remain undefined and the increasing optical density is not adequately developed in the experiment. |
| D06 | Water in petroleum; remote analyzer/fiber interface; clarify before equipment selection. | Internally inconsistent. Decision text names ATR-IR, recommendation/experiment name NIR, and rationale cites a kidney-study NIR spectrum. Petroleum application evidence was in the ledger but was not used for the recommendation rationale. |
| D07 | Hot polymer/API extrusion; offline assays; hot interface and build-up; compare before probe selection. | Failed content despite complete status. Contexts are empty and retrieval is skipped. The generated clarification response does not provide a grounded comparison of interface/measurement concepts from available evidence. |
| D08 | Laboratory classification of model tissues; compare MIR ATR/fluorescence while controlling spatial mismatch. | Latest attempts incomplete: provider unavailable during synthesis. An older successful answer compares individual and combined methods and groups specimens, but includes concentration/detection-limit boilerplate and calls for undefined quality variables even though tissue classes and a classification goal were supplied. One later extraction even uses `ATR` as sample phase. |

## Final enquiries

| Case | What the enquiry requires | Canonical result and targeted observations |
|---|---|---|
| H01 | Changed API/excipient formulation; assess old NIR calibration reuse and the claim that Raman preserves validity. | Canonical answer fails: extraction is empty, no retrieval, generic questions repeat supplied facts. Targeted rerun reaches retrieval but assumes similar optical properties and still does not adequately answer the calibration-transfer/Raman claim. |
| H02 | Two dairy streams with different optical properties; appropriate first concepts and interface comparison using relevant lab protein/fat results. | Partial. Two streams and transmission/reflection candidates retained. Both recommendations cite the reflection passage, although the transmission/comparison passage was retrieved. The experiment assigns one geometry per stream instead of comparing applicable interfaces. |
| H03 | Challenge unsupported direct fluorescence measurement of glucose/viable biomass, with no target/marker/reference relationship. | Main uncertainty conclusion is appropriate. Needs clearer distinction between direct analyte response and marker-based or indirect calibrated relationships, plus more specific control/reference experiments and risks. |
| H04 | Assess remote MIR ATR concept and reuse of an existing visible/NIR silica cable. | Useful caution, incomplete justification. Does not approve reuse, but selected rationale is generic ATR capability and risks repeat cost. The relevant cable passage was found by Qdrant but rejected by facet classification. |
| H05 | Unidentified contamination in a liquid process; define information and characterization before exact method/configuration selection. | Main refusal to select exact equipment is appropriate. Canonical extraction omits the context and skips retrieval. Targeted rerun retains the liquid context and gives a more appropriate on/off-spec characterization plan. |
| H06 | Assess whether the supplied kidney study proves readiness for live surgical boundary decisions, given no new in-vivo/setup validation. | Failed content. No context, no retrieval and generic answer claiming absent evidence. The kidney study is in the active corpus and direct search finds it. The targeted rerun repeats empty extraction and no search. |

## Cross-scenario findings

1. Unknown exact composition or numeric conditions are repeatedly confused with
   no useful measurement context. D07, H01, H05 and H06 expose the retrieval gate.
2. Quote membership checks accept semantically wrong field assignments: `opaque`
   or `ATR` can pass as sample phase because each appears in the source wording.
3. Method names found anywhere in a selected record are used as allowed choices.
   That does not establish matrix, target or geometry suitability. D04-D06 show
   especially clear examples of relevant-sounding method labels with irrelevant
   source rationales.
4. Generic experiment assembly assumes analyte-style reference assays, concentration
   ranges and acceptable/off-spec states even for tissue classification. D08
   requires class labels, spatial alignment and specimen-level evaluation rather
   than a generic concentration-calibration template.
5. Relevant records can be retrieved but not cited for the right proposition.
   H02 and D06 demonstrate a synthesis/evidence-use failure, independent of whether
   the vector database returned useful hits.
6. Relaxed field recovery preserves a quoted original when the model paraphrases,
   but it cannot repair missing contexts or decide whether a quote belongs in the
   correct typed field. Retrieval orchestration and answer planning need attention.

## Priority of follow-up work

- Preserve and search original grounded enquiry content when extraction is sparse;
  keep diagnostic warnings out of scientific queries.
- Normalize source/query vocabulary consistently and retain compatibility evidence.
- Distinguish phases, appearances, geometries, analytes, classification labels,
  existing equipment and proposed methods in extraction and downstream planning.
- Associate rationale support with the requested matrix, target and geometry,
  rather than accepting a same-family method mention from another application.
- Build experiments around the task: method/interface comparison, calibration
  transfer, unknown-contaminant characterization or research classification.
- Report run completeness separately from input coverage and answer adequacy;
  preserve partial useful answers and visible gaps.

Do not manually rewrite the generated envelopes or assemble a final submission
from favorable single-case reruns. After general corrections, rerun complete
development and final suites under recorded configurations.
