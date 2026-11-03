import assert from 'node:assert/strict'
import { test } from 'vitest'

import { isAssessmentRun, reportText, contextLabel, compactRequirements, usefulClarificationReason, composeEnquiry, clarificationKey, displayText, chemistWarnings } from '../src/features/assessment/assessment'

function runFixture() {
  return {
    run_status: 'complete', facts: { contexts: [], customer_claims_and_requests: [], shared_constraints: [], missing_information: [], fact_provenance: [] },
    retrieval: { status: 'ok', corpus_version: 'corpus-test', retrieval_version: 'retrieval-test', ranking: 'test', semantic_min_score: .65, max_records: 8, search_rounds: 0, model_calls: 0, warnings: [], evidence: [], queries: [], coverage: [], gaps: [] },
    assessment: {
      decision_status: 'insufficient_information', decision_reason: 'A target has not been defined.', case_summary: 'The customer requests initial characterization.',
      requirements: { stated: [], unknowns: ['Target variable'] }, clarification_questions: [{ priority: 1, context_ids: [], question: 'What is the target variable?', reason: { text: 'The target is unknown.', evidence_ids: [] }, affects: ['Method selection'] }], recommendations: [], risks: [], source_index: [],
      experiment: { context_ids: [], objective: 'Characterize the material.', samples: ['Representative samples'], measurements: ['Independent reference characterization'], comparisons: [], validation: 'Hold out independent material.', decision_criteria: 'Agree criteria with customer.', open_items: ['Define target'], variation: ['Material variation'], proposed_settings: [], validation_groups: [], acceptance_criteria: [] },
    },
    errors: [], warnings: [],
    metadata: { run_id: 'test-run', generated_at: '2026-10-18T00:00:00Z', pipeline_version: 'test', provider: 'test', model: 'test', returned_models: {}, endpoint: 'https://example.test', corpus_version: 'corpus-test', retrieval_version: 'retrieval-test', prompt_versions: {}, prompt_sha256: {}, schema_sha256: {}, stage_elapsed_s: {}, last_successful_call_usage: {}, call_timeout_s: 30, request_deadline_s: 90, provider_max_retries: 2, provider_max_completion_tokens: 4096, extraction_max_completion_tokens: 3072, synthesis_max_completion_tokens: 4096, synthesis_temperature: 0, repair_counts: {}, provider_mode: 'auto', stage_providers: {}, provider_attempts: [] },
  }
}

test('an empty supported shortlist is a complete scientific decision and exports without modification', () => {
  const run = runFixture()
  run.retained_extension = { future_metadata: ['preserve me'] }
  const before = JSON.stringify(run)
  assert.equal(isAssessmentRun(run), true)
  const report = reportText(run, ' Original enquiry\nwith whitespace ')
  assert.doesNotMatch(report, /Run: test-run/)
  assert.match(report, /No supported method shortlist/)
  assert.match(report, /What is the target variable/)
  assert.match(report, /Characterize the material/)
  assert.ok(report.includes(' Original enquiry\nwith whitespace '))
  assert.equal(JSON.stringify(run), before)
})

test('Gemini assessments retain enquiry lineage and question identifiers', () => {
  const run = runFixture()
  Object.assign(run.metadata, { provider:'gemini', provider_mode:'gemini', model:'gemini-3.8-flash',
    enquiry_id:'enquiry', parent_run_id:'parent', round_no:2, question_ids:['question'] })
  assert.equal(isAssessmentRun(run), true)
  assert.equal(run.metadata.parent_run_id, 'parent')
})

test('incomplete envelopes require errors and cannot contain an assessment or orphan retrieval', () => {
  const run = runFixture()
  run.run_status = 'incomplete'; run.assessment = null
  assert.equal(isAssessmentRun(run), false)
  run.errors = [{ code: 'synthesis_timeout', stage: 'synthesis', message: 'Try again.', http_status: 504 }]
  assert.equal(isAssessmentRun(run), true)
  assert.match(reportText(run, 'Enquiry'), /Incomplete run — no technical assessment/)
  assert.match(reportText(run, 'Enquiry'), /synthesis_timeout/)
  run.facts = null
  assert.equal(isAssessmentRun(run), false)
  run.retrieval = null
  assert.equal(isAssessmentRun(run), true)
  run.assessment = runFixture().assessment
  assert.equal(isAssessmentRun(run), false)
})

test('malformed nested fields and inconsistent run states are rejected before rendering', () => {
  const changes = [
    r => { r.assessment.experiment.validation_groups = null },
    r => { r.facts.contexts = [null] },
    r => { r.assessment.clarification_questions[0].reason.evidence_ids = 'S01' },
    r => { r.assessment.decision_status = 'certain' },
    r => { r.assessment.decision_status = 'provisional' },
    r => { r.assessment.clarification_questions = [] },
    r => { r.metadata.stage_elapsed_s = { extraction: 'fast' } },
    r => { r.errors = [{ stage: 'synthesis', code: 'failed', message: 'Failed', http_status: 502 }] },
  ]
  for (const change of changes) {
    const run = runFixture(); change(run)
    assert.equal(isAssessmentRun(run), false)
  }
  for (const value of [null, [], 'wrong service', { run_status: 'complete' }]) assert.equal(isAssessmentRun(value), false)
})

test('claim references must resolve to the pinned evidence, not another revision', () => {
  const run = runFixture()
  run.assessment.clarification_questions[0].reason.evidence_ids = ['S01:p1']
  assert.equal(isAssessmentRun(run), false)
  const evidence = { evidence_id: 'S01:p1', source_id: 'S01', file_name: 'source.pdf', source_sha256: 'a'.repeat(64), page: 1, section: 'Scope', text: 'Research demonstration.', content_kind: 'verbatim_text', evidence_scope: 'research_demonstration', revision: 'rev1', validation_status: 'passed', human_review_status: 'not_reviewed', retrieval_eligible: true, issues: [], corpus_version: 'corpus-test', evidence_url: '/api/evidence/S01:p1' }
  run.retrieval.evidence = [{ evidence, context_ids: [], facets: [], matches: [], score: 0, selection_reasons: [] }]
  run.assessment.source_index = [{ ...evidence, citation: 'S01 p.1', sheet: null, row: null }]
  assert.equal(isAssessmentRun(run), true)
  assert.match(reportText(run, 'Enquiry'), /Research demonstration/)
  assert.match(reportText(run, 'Enquiry'), /S01 p.1/)
  run.assessment.source_index[0].revision = 'rev2'
  assert.equal(isAssessmentRun(run), false)
})

test('identically labeled streams remain distinguishable', () => {
  const facts = { contexts: [{ context_id: 'stream_1', label: 'Liquid' }, { context_id: 'stream_2', label: 'Liquid' }] }
  assert.equal(contextLabel(facts, ['stream_1']), 'Liquid (first stream)')
  assert.equal(contextLabel(facts, ['stream_2']), 'Liquid (second stream)')
  assert.equal(contextLabel(facts, []), 'Shared / all contexts')
})

test('requirements stay concise without losing stated values, units or original provenance', () => {
  const rows = [
    ['label', 'petroleum stream'], ['target_analytes', 'water'], ['sample_matrix', 'petroleum stream'],
    ['sample_phase', 'liquid'], ['appearance', 'opaque'], ['temperature', '40–80 °C'],
    ['response_time_raw', 'less than 10 seconds'], ['response_time_s', '10'],
    ['required_error', '±0.1 wt%'], ['reference_assays', 'Karl Fischer titration'],
    ['reference_assays', 'Karl Fischer titration'],
  ].map(([field, value]) => ({ context_id: 'stream_1', field, value, field_path: `/contexts/0/${field}`, origin: 'customer', input_quote: value }))
  const original = structuredClone(rows)
  const summary = compactRequirements(rows, 'petroleum stream')
  assert.deepEqual(summary, [
    { label: 'Measure', values: ['water'] }, { label: 'Sample', values: ['liquid', 'opaque'] },
    { label: 'Temperature', values: ['40–80 °C'] }, { label: 'Response time', values: ['less than 10 seconds'] },
    { label: 'Required accuracy', values: ['±0.1 wt%'] }, { label: 'Reference method', values: ['Karl Fischer titration'] },
  ])
  assert.deepEqual(rows, original)
  const targetMatchesHeading = [{ ...rows[1], value: 'water' }]
  assert.deepEqual(compactRequirements(targetMatchesHeading, 'water'), [{ label: 'Measure', values: ['water'] }])
})

test('generic clarification boilerplate is omitted but useful or cited reasoning is retained', () => {
  const run = runFixture()
  const question = run.assessment.clarification_questions[0]
  question.reason.text = 'Customer clarification is needed before finalizing the proposed feasibility study.'
  assert.equal(usefulClarificationReason(question), false)
  assert.ok(!reportText(run, 'Enquiry').includes(question.reason.text))
  question.reason.evidence_ids = ['S01:p1']
  assert.equal(usefulClarificationReason(question), true)
  question.reason = { text: 'Water absorption can require a different optical path for this matrix.', evidence_ids: [] }
  assert.equal(usefulClarificationReason(question), true)
})

test('clarification submission preserves original input and explicitly attributes answers to their questions', () => {
  const description = ' Original enquiry\nwith customer wording '
  const answers = [{ question: 'Moisture range?', context: 'Powder', answer: ' 0–5 wt% ' }, { question: 'Accuracy?', context: 'Powder', answer: '\n ' }]
  const before = structuredClone(answers)
  assert.equal(composeEnquiry(description, []), description)
  const result = composeEnquiry(description, answers)
  assert.ok(result.startsWith(description + '\n\nCustomer clarifications:'))
  assert.ok(result.includes('Context: Powder\nQuestion: Moisture range?\nAnswer:  0–5 wt% '))
  assert.ok(!result.includes('Accuracy?'))
  assert.deepEqual(answers, before)
  assert.equal(composeEnquiry(description, [{ ...answers[0], answer: '2–6 wt%' }]).match(/Question:/g).length, 1)
})

test('answer identity survives question reorder but cannot leak between different streams', () => {
  const q = runFixture().assessment.clarification_questions[0]
  assert.equal(clarificationKey({ ...q, context_ids: ['stream_1', 'stream_2'] }), clarificationKey({ ...q, context_ids: ['stream_2', 'stream_1'], priority: 9 }))
  assert.notEqual(clarificationKey({ ...q, context_ids: ['stream_1'] }), clarificationKey({ ...q, context_ids: ['stream_2'] }))
})

test('chemist presentation removes internal identifiers and technical diagnostics but preserves science', () => {
  assert.equal(displayText('Proposed (stream_1): method_no T01 at /contexts/0/temperature'), 'Proposed: method the listed test at the specified requirement')
  assert.deepEqual(chemistWarnings([
    'The matrix may fluoresce and requires confirmation.',
    'Semantic similarity threshold was not met.',
    'The matrix may fluoresce and requires confirmation.',
  ]), ['The matrix may fluoresce and requires confirmation.'])
})
