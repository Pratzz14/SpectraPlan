// Public F06 contracts. Keep the received object intact for lossless JSON export.
export interface AssessmentRequest { description: string; fact_overrides?: null; clarification_answers?: ClarificationAnswer[]; enquiry_id?: string; parent_run_id?: string }
export interface ClarificationAnswer { question: string; context: string; answer: string; question_id?: string | null; origin_run_id?: string | null }
export function composeEnquiry(description: string, answers: ClarificationAnswer[]): string {
  const filled = answers.filter(item => item.answer.trim());
  return filled.length ? `${description}\n\nCustomer clarifications:\n\n${filled.map(item => `Context: ${item.context}\nQuestion: ${item.question}\nAnswer: ${item.answer}`).join('\n\n')}` : description;
}
export function clarificationKey(question: ClarificationQuestion): string {
  return JSON.stringify([[...question.context_ids].sort(), question.question]);
}
export interface MeasurementContext {
  context_id: string; label: string; target_analytes: string[]; measurement_goals: string[];
  sample_matrix: string | null; sample_phase: string | null; appearance: string | null;
  temperature: string | null; pressure: string | null; response_time_raw: string | null;
  response_time_s: number | null; concentration_range: string | null; required_error: string | null;
  reference_assays: string[]; process_constraints: string[]; missing_information: string[];
}
export interface CaseFacts {
  contexts: MeasurementContext[];
  customer_claims_and_requests: { text: string; kind: 'reported_fact' | 'requested_outcome' | 'proposed_approach' | 'customer_claim'; context_ids: string[]; input_quote: string }[];
  shared_constraints: string[]; missing_information: string[];
  fact_provenance: { field_path: string; context_ids: string[]; input_quote: string }[];
}
export interface Assertion { text: string; evidence_ids: string[] }
export interface SpectralRange extends Assertion {
  kind: 'nominal_method_range' | 'source_configuration_range' | 'undetermined';
  interval: string | null; raman_excitation: Assertion | null; raman_shift: Assertion | null;
}
export interface Recommendation {
  context_ids: string[]; method: string; geometry: string | null; measurement_location: string | null;
  spectral_range: SpectralRange; rationale: Assertion; assumptions: string[]; limitations: Assertion[];
  status: 'worth_testing' | 'conditional_on_clarification';
}
export interface ClarificationQuestion {
  priority: number; context_ids: string[]; question: string; reason: Assertion; affects: string[];
}
export interface Requirement {
  context_id: string | null; field: string; field_path: string; value: string; origin: 'customer'; input_quote: string;
}
export interface Experiment {
  context_ids: string[]; objective: string; samples: string[]; measurements: string[]; comparisons: string[];
  validation: string; decision_criteria: string; open_items: string[]; variation: string[];
  proposed_settings: { context_ids: string[]; name: string; value: number; unit: string | null; origin: 'proposed' }[];
  validation_groups: { context_ids: string[]; independent_unit: 'batch' | 'run' | 'specimen' | 'patient' | 'unresolved'; study_type: 'targeted_feasibility' | 'characterization' }[];
  acceptance_criteria: { context_id: string; metric: 'required_error' | 'response_time_raw' | 'bias' | 'robustness'; threshold: string | null; requirement_path: string | null; origin: 'customer' | 'unknown' }[];
}
export interface SourceReference {
  evidence_id: string; citation: string; source_id: string; file_name: string; source_sha256: string;
  page: number | null; sheet: string | null; row: number | null; revision: string; corpus_version: string; evidence_url: string;
}
export interface Assessment {
  decision_status: 'provisional' | 'insufficient_information' | 'outside_supported_scope';
  decision_reason: string; case_summary: string; requirements: { stated: Requirement[]; unknowns: string[] };
  clarification_questions: ClarificationQuestion[]; recommendations: Recommendation[];
  risks: (Assertion & { context_ids: string[] })[]; experiment: Experiment; source_index: SourceReference[];
}
export interface ResolvedEvidence {
  evidence_id: string; source_id: string; file_name: string; source_sha256: string; page: number | null;
  section: string; text: string; content_kind: 'verbatim_text' | 'figure_transcription' | 'method_row' | 'llm_knowledge' | 'extracted_text';
  evidence_scope: 'general_method' | 'application_example' | 'research_demonstration' | 'business_context';
  revision: string; validation_status: 'passed' | 'flagged'; human_review_status: 'not_reviewed' | 'verified' | 'rejected';
  retrieval_eligible: boolean; issues: string[]; corpus_version: string; evidence_url: string;
  sheet?: string; row?: number;
  region?: { x0: number; y0: number; x1: number; y1: number; label: string } | null;
  workbook_notes?: { source_id: string; sheet: string; row: number; text: string }[] | null;
  [key: string]: unknown;
}
type Facet = 'application' | 'geometry' | 'compatibility' | 'limitations';
interface EvidenceMatch {
  query_id: string; context_id: string; facets: Facet[]; admission: 'lexical' | 'semantic_only' | 'structured';
  bm25_score: number | null; bm25_rank: number | null; cosine_score: number | null; dense_rank: number | null;
  rrf_score: number; matched_terms: string[]; matching_segment: string | null;
}
export interface RetrievalResult {
  status: 'ok'; corpus_version: string; retrieval_version: string; ranking: string; semantic_min_score: number;
  max_records: number; search_rounds: number; model_calls: number; warnings: string[];
  evidence: { evidence: ResolvedEvidence; context_ids: string[]; facets: Facet[]; matches: EvidenceMatch[]; score: number; selection_reasons: string[] }[];
  queries: { query_id: string; context_id: string; facet: string; round: number; query: string; source_fields: Record<string, string[]>; omitted_terms: string[]; expanded_terms: string[]; statements: Record<string, unknown>[]; candidates: { evidence_id: string; admitted: boolean; reason: string; match: EvidenceMatch }[] }[];
  coverage: { context_id: string; facet: Facet; status: 'candidate_found' | 'gap'; evidence_ids: string[] }[];
  gaps: { context_id: string | null; facet: Facet | null; reason: 'no_relevant_evidence' | 'budget_limit' | 'missing_context' | 'unspecified_input'; message: string }[];
}
export interface AssessmentMetadata {
  run_id: string; generated_at: string; pipeline_version: string; provider: string; model: string;
  returned_models: Record<string, string | null>; endpoint: string; corpus_version: string | null; retrieval_version: string | null;
  prompt_versions: Record<string, string>; prompt_sha256: Record<string, string>; schema_sha256: Record<string, string>;
  stage_elapsed_s: Record<string, number>; last_successful_call_usage: Record<string, Record<string, number>>;
  call_timeout_s: number; request_deadline_s: number; provider_max_retries: number; provider_max_completion_tokens: number;
  extraction_max_completion_tokens: number; synthesis_max_completion_tokens: number; synthesis_temperature: number;
  repair_counts: Record<string, number>; provider_mode: 'dashscope' | 'auto' | 'gemini' | 'groq' | 'llmtech';
  enquiry_id?: string | null; parent_run_id?: string | null; round_no?: number; question_ids?: string[];
  stage_providers: Record<string, Record<string, unknown>>; provider_attempts: Record<string, unknown>[];
}
export interface RunError { code: string; stage: 'extraction' | 'retrieval' | 'synthesis'; message: string; http_status: 502 | 503 | 504 }
export interface AssessmentRun {
  run_status: 'complete' | 'incomplete'; facts: CaseFacts | null; retrieval: RetrievalResult | null;
  assessment: Assessment | null; errors: RunError[]; metadata: AssessmentMetadata; warnings: string[];
}
export interface EnquirySummary {
  enquiry_id: string; original_description: string; created_at: string; updated_at: string; rounds: number; latest_run_id: string;
}
export interface EnquiryDetail {
  enquiry_id: string; original_description: string;
  runs: { run_id: string; created_at: string; status: string; round_no: number; parent_run_id: string | null }[];
}
export interface ExplainabilityTrace {
  run_id: string; created_at: string; description: string; clarification_answers: ClarificationAnswer[];
  enquiry_id: string; parent_run_id: string | null; round_no: number;
  status: 'running' | 'complete' | 'incomplete' | 'interrupted'; draft_description: string;
  questions: (ClarificationQuestion & { question_id: string; origin_run_id: string })[];
  run: AssessmentRun | null;
  legacy_run?: unknown;
  events: { sequence: number; stage: string; event_type: string; created_at: string; payload: Record<string, unknown> }[];
}

// Small boundary validators: validate before rendering, without normalizing or stripping export data.
type Check = (value: unknown) => boolean;
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const text: Check = v => typeof v === 'string';
const number: Check = v => typeof v === 'number' && Number.isFinite(v);
const boolean: Check = v => typeof v === 'boolean';
const enumeration = (...values: unknown[]): Check => v => values.includes(v);
const nullable = (check: Check): Check => v => v === null || check(v);
const optional = (check: Check): Check => v => v === undefined || check(v);
const list = (check: Check): Check => v => Array.isArray(v) && v.every(check);
const shape = (fields: Record<string, Check>): Check => v => object(v) && Object.entries(fields).every(([key, check]) => check(v[key]));
const dictionary = (check: Check): Check => v => object(v) && Object.values(v).every(check);
const strings = list(text), nullText = nullable(text), nullNumber = nullable(number);
const assertion = shape({ text, evidence_ids: strings });
const facet = enumeration('application', 'geometry', 'compatibility', 'limitations');
const match = shape({ query_id: text, context_id: text, facets: list(facet), admission: enumeration('lexical', 'semantic_only', 'structured'), bm25_score: nullNumber, bm25_rank: nullNumber, cosine_score: nullNumber, dense_rank: nullNumber, rrf_score: number, matched_terms: strings, matching_segment: nullText });
const context = shape({ context_id: text, label: text, target_analytes: strings, measurement_goals: strings, sample_matrix: nullText, sample_phase: nullText, appearance: nullText, temperature: nullText, pressure: nullText, response_time_raw: nullText, response_time_s: nullNumber, concentration_range: nullText, required_error: nullText, reference_assays: strings, process_constraints: strings, missing_information: strings });
const facts = shape({ contexts: list(context), customer_claims_and_requests: list(shape({ text, kind: enumeration('reported_fact', 'requested_outcome', 'proposed_approach', 'customer_claim'), context_ids: strings, input_quote: text })), shared_constraints: strings, missing_information: strings, fact_provenance: list(shape({ field_path: text, context_ids: strings, input_quote: text })) });
const source = shape({ evidence_id: text, citation: text, source_id: text, file_name: text, source_sha256: text, page: nullNumber, sheet: nullText, row: nullNumber, revision: text, corpus_version: text, evidence_url: text });
const evidence = shape({ evidence_id: text, source_id: text, file_name: text, source_sha256: text, page: nullNumber, section: text, text, content_kind: enumeration('verbatim_text', 'figure_transcription', 'method_row', 'llm_knowledge', 'extracted_text'), evidence_scope: enumeration('general_method', 'application_example', 'research_demonstration', 'business_context'), revision: text, validation_status: enumeration('passed', 'flagged'), human_review_status: enumeration('not_reviewed', 'verified', 'rejected'), retrieval_eligible: boolean, issues: strings, corpus_version: text, evidence_url: text, sheet: optional(text), row: optional(number), region: optional(nullable(shape({ x0: number, y0: number, x1: number, y1: number, label: text }))), workbook_notes: optional(nullable(list(shape({ source_id: text, sheet: text, row: number, text })))) });
const retrieval = shape({ status: enumeration('ok'), corpus_version: text, retrieval_version: text, ranking: text, semantic_min_score: number, max_records: number, search_rounds: number, model_calls: number, warnings: strings, evidence: list(shape({ evidence, context_ids: strings, facets: list(facet), matches: list(match), score: number, selection_reasons: strings })), queries: list(shape({ query_id: text, context_id: text, facet: enumeration('context', 'application', 'geometry', 'compatibility', 'limitations', 'method_table'), round: number, query: text, source_fields: dictionary(strings), omitted_terms: strings, expanded_terms: strings, statements: list(object), candidates: list(shape({ evidence_id: text, admitted: boolean, reason: text, match })) })), coverage: list(shape({ context_id: text, facet, status: enumeration('candidate_found', 'gap'), evidence_ids: strings })), gaps: list(shape({ context_id: nullText, facet: nullable(facet), reason: enumeration('no_relevant_evidence', 'budget_limit', 'missing_context', 'unspecified_input'), message: text })) });
const experiment = shape({ context_ids: strings, objective: text, samples: strings, measurements: strings, comparisons: strings, validation: text, decision_criteria: text, open_items: strings, variation: strings, proposed_settings: list(shape({ context_ids: strings, name: text, value: number, unit: nullText, origin: enumeration('proposed') })), validation_groups: list(shape({ context_ids: strings, independent_unit: enumeration('batch', 'run', 'specimen', 'patient', 'unresolved'), study_type: enumeration('targeted_feasibility', 'characterization') })), acceptance_criteria: list(shape({ context_id: text, metric: enumeration('required_error', 'response_time_raw', 'bias', 'robustness'), threshold: nullText, requirement_path: nullText, origin: enumeration('customer', 'unknown') })) });
const spectralRange: Check = v => shape({ text, evidence_ids: strings, kind: enumeration('nominal_method_range', 'source_configuration_range', 'undetermined'), interval: nullText, raman_excitation: nullable(assertion), raman_shift: nullable(assertion) })(v) && object(v) && (v.kind === 'undetermined' ? v.interval === null : typeof v.interval === 'string');
const assessment = shape({ decision_status: enumeration('provisional', 'insufficient_information', 'outside_supported_scope'), decision_reason: text, case_summary: text, requirements: shape({ stated: list(shape({ context_id: nullText, field: text, field_path: text, value: text, origin: enumeration('customer'), input_quote: text })), unknowns: strings }), clarification_questions: list(shape({ priority: number, context_ids: strings, question: text, reason: assertion, affects: strings })), recommendations: list(shape({ context_ids: strings, method: text, geometry: nullText, measurement_location: nullText, spectral_range: spectralRange, rationale: assertion, assumptions: strings, limitations: list(assertion), status: enumeration('worth_testing', 'conditional_on_clarification') })), risks: list(v => assertion(v) && shape({ context_ids: strings })(v)), experiment, source_index: list(source) });
const metadata = shape({ run_id: text, generated_at: text, pipeline_version: text, provider: text, model: text, returned_models: dictionary(nullText), endpoint: text, corpus_version: nullText, retrieval_version: nullText, prompt_versions: dictionary(text), prompt_sha256: dictionary(text), schema_sha256: dictionary(text), stage_elapsed_s: dictionary(number), last_successful_call_usage: dictionary(dictionary(number)), call_timeout_s: number, request_deadline_s: number, provider_max_retries: number, provider_max_completion_tokens: number, extraction_max_completion_tokens: number, synthesis_max_completion_tokens: number, synthesis_temperature: number, repair_counts: dictionary(number), provider_mode: enumeration('dashscope', 'auto', 'gemini', 'groq', 'llmtech'), stage_providers: dictionary(object), provider_attempts: list(object) });
const envelope = shape({ run_status: enumeration('complete', 'incomplete'), facts: nullable(facts), retrieval: nullable(retrieval), assessment: nullable(assessment), errors: list(shape({ code: text, stage: enumeration('extraction', 'retrieval', 'synthesis'), message: text, http_status: enumeration(502, 503, 504) })), metadata, warnings: strings });

export function isAssessmentRun(value: unknown): value is AssessmentRun {
  if (!envelope(value)) return false;
  const run = value as AssessmentRun;
  if (run.retrieval && !run.facts) return false;
  if (run.run_status === 'incomplete') return run.assessment === null && run.errors.length > 0;
  if (!run.facts || !run.retrieval || !run.assessment || run.errors.length) return false;
  const result = run.assessment;
  if (!result.recommendations.length && (result.decision_status === 'provisional' || !result.clarification_questions.length)) return false;
  const ledger = new Map(run.retrieval.evidence.map(entry => [entry.evidence.evidence_id, entry.evidence]));
  const references = new Map(result.source_index.map(ref => [ref.evidence_id, ref]));
  if (ledger.size !== run.retrieval.evidence.length || references.size !== result.source_index.length) return false;
  if (!result.source_index.every(ref => {
    const record = ledger.get(ref.evidence_id);
    return record && record.revision === ref.revision && record.corpus_version === ref.corpus_version && record.source_sha256 === ref.source_sha256;
  })) return false;
  const assertions = [...result.clarification_questions.map(q => q.reason), ...result.risks,
    ...result.recommendations.flatMap(r => [r.rationale, r.spectral_range, ...r.limitations, ...[r.spectral_range.raman_excitation, r.spectral_range.raman_shift].filter((a): a is Assertion => a !== null)])];
  return assertions.every(a => a.evidence_ids.every(id => references.has(id) && ledger.has(id)));
}

export const readable = (value: string) => value
  .replaceAll('_', ' ')
  .replace(/\b\w/g, character => character.toUpperCase());

const technicalDiagnosticPatterns = [
  /semantic similarity/i, /similarity threshold/i, /automated validation/i,
  /agent inspection/i, /retrieval coverage/i, /internal source check/i,
  /source check/i, /corpus version/i, /pipeline version/i, /prompt/i,
  /embedding/i, /cosine score/i, /bm25/i, /rrf/i, /retrieval round/i,
  /debug/i, /json path/i,
];

export function displayText(value: string): string {
  return value
    .replace(/\s*\(customer requirement \/(?:contexts|shared_constraints)[^)]*\)/g, '')
    .replace(/\bresponse_time_raw\b/g, 'response time')
    .replace(/\brequired_error\b/g, 'required accuracy')
    .replace(/\bProposed\s*\([^)]*\)\s*:\s*/gi, 'Proposed: ')
    .replace(/\bstream_\d+\b/gi, 'this stream')
    .replace(/\bmethod_no\b/gi, 'method')
    .replace(/\bT\d{2,}\b/g, 'the listed test')
    .replace(/\/(?:contexts|requirements|experiment)(?:\/[^)\s,;:]+)+/g, 'the specified requirement')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

export function uniqueDisplayItems(items: string[]): string[] {
  const seen = new Set<string>();
  return items.map(displayText).filter(item => {
    const key = item.toLowerCase();
    if (!item || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function isTechnicalDiagnostic(value: string): boolean {
  return technicalDiagnosticPatterns.some(pattern => pattern.test(value));
}

export function chemistWarnings(items: string[]): string[] {
  return uniqueDisplayItems(items).filter(item => !isTechnicalDiagnostic(item));
}

const requirementLabels: Record<string, string> = {
  target_analytes: 'Measure', measurement_goals: 'Goal', sample_matrix: 'Sample', sample_phase: 'Sample',
  appearance: 'Sample', temperature: 'Temperature', pressure: 'Pressure', response_time_raw: 'Response time',
  concentration_range: 'Concentration range', required_error: 'Required accuracy', reference_assays: 'Reference method',
  process_constraints: 'Process constraints', shared_constraints: 'Shared constraints',
};

export function requirementLabel(field: string): string {
  return requirementLabels[field] ?? readable(field);
}

export function compactRequirements(rows: Requirement[], contextName: string): { label: string; values: string[] }[] {
  const groups = new Map<string, string[]>();
  for (const row of rows) {
    // The context heading already supplies its label; normalized timing duplicates the raw requirement.
    if (['label', 'context_id', 'response_time_s'].includes(row.field)
      || (row.field === 'sample_matrix' && row.value.trim().toLowerCase() === contextName.trim().toLowerCase())) continue;
    const label = requirementLabel(row.field);
    const values = groups.get(label) ?? [];
    const value = displayText(row.value);
    if (!values.some(existing => existing.trim().toLowerCase() === value.trim().toLowerCase())) values.push(value);
    groups.set(label, values);
  }
  return Array.from(groups, ([label, values]) => ({ label, values }));
}

export function usefulClarificationReason(question: ClarificationQuestion): boolean {
  // Never suppress cited reasoning. This exact uncited fallback adds nothing to a question's purpose.
  if (question.reason.evidence_ids.length) return true;
  const normalize = (value: string) => value.trim().replace(/\s+/g, ' ').replace(/[.!?]+$/, '').toLowerCase();
  const reason = normalize(question.reason.text);
  return reason !== normalize('Customer clarification is needed before finalizing the proposed feasibility study.')
    && reason !== normalize(question.question);
}

export function contextLabel(facts: CaseFacts | null, ids: string[]): string {
  return ids.length ? ids.map(id => {
    const label = facts?.contexts.find(c => c.context_id === id)?.label ?? readable(id)
    const matches = facts?.contexts.filter(c => c.label === label) ?? []
    const ordinal = ['first', 'second', 'third', 'fourth'][matches.findIndex(c => c.context_id === id)] ?? 'additional'
    return matches.length > 1 ? `${label} (${ordinal} stream)` : label
  }).join(' · ') : 'Shared / all contexts';
}

export function reportText(run: AssessmentRun, description: string): string {
  const a = run.assessment;
  const lines = ['SpectraPlan — Initial technical assessment', '', 'Submitted enquiry', description];
  const add = (title: string, items: string[]) => { const clean = uniqueDisplayItems(items); if (clean.length) lines.push('', title, ...clean.map(item => `- ${item}`)); };
  const cited = (claim: Assertion) => `${displayText(claim.text)}${claim.evidence_ids.length ? ` [${claim.evidence_ids.map(id => a?.source_index.find(ref => ref.evidence_id === id)?.citation ?? 'Source').join('; ')}]` : ''}`;
  const scoped = (ids: string[]) => contextLabel(run.facts, ids);
  if (a) {
    lines.push('', `Decision: ${readable(a.decision_status)}`, displayText(a.decision_reason), '', displayText(a.case_summary));
    add('Customer-stated requirements', a.requirements.stated.map(r => `${scoped(r.context_id ? [r.context_id] : [])} · ${requirementLabel(r.field)}: ${displayText(r.value)} (customer quote: “${displayText(r.input_quote)}”)`));
    add('Unknowns', a.requirements.unknowns);
    add('Clarification questions', [...a.clarification_questions].sort((x, y) => x.priority - y.priority).map(q => `Priority ${q.priority} · ${scoped(q.context_ids)}: ${q.question}${usefulClarificationReason(q) ? `\n  Why: ${cited(q.reason)}` : ''}\n  Affects: ${q.affects.join(', ') || 'Not specified'}`));
    if (!a.recommendations.length) lines.push('', 'No supported method shortlist. Resolve the questions and follow the proposed investigation.');
    for (const r of a.recommendations) {
      lines.push('', `${displayText(r.method)} · ${readable(r.status)} · ${scoped(r.context_ids)}`, `Geometry: ${displayText(r.geometry ?? 'Unknown')}`, `Measurement location: ${displayText(r.measurement_location ?? 'Unknown')}`, `Range (${readable(r.spectral_range.kind)}): ${displayText(r.spectral_range.interval ?? 'Undetermined')}`, cited(r.spectral_range), `Rationale: ${cited(r.rationale)}`);
      if (r.spectral_range.raman_excitation) lines.push(`Raman excitation: ${cited(r.spectral_range.raman_excitation)}`);
      if (r.spectral_range.raman_shift) lines.push(`Raman shift: ${cited(r.spectral_range.raman_shift)}`);
      add('Assumptions', r.assumptions); add('Limitations', r.limitations.map(cited));
    }
    add('Risks and limitations', a.risks.map(r => `${scoped(r.context_ids)}: ${cited(r)}`));
    const e = a.experiment;
    lines.push('', `Proposed feasibility experiment · ${scoped(e.context_ids)}`, e.objective);
    add('Samples', e.samples); add('Measurements and reference assays', e.measurements); add('Comparisons', e.comparisons); add('Variation to cover', e.variation);
    lines.push('', 'Validation', e.validation);
    add('Independent validation groups', e.validation_groups.map(g => `${scoped(g.context_ids)}: ${readable(g.study_type)}, independent unit: ${g.independent_unit}`));
    add('Proposed settings — not customer requirements or measured results', e.proposed_settings.map(s => `${scoped(s.context_ids)}: ${s.name} = ${s.value}${s.unit ? ` ${s.unit}` : ''}`));
    add('Acceptance criteria', e.acceptance_criteria.map(c => `${scoped([c.context_id])} · ${readable(c.metric)}: ${c.threshold ?? 'Unknown — agree with customer'} (${c.origin})`));
    lines.push('', 'Go / no-go decision', e.decision_criteria); add('Open items', e.open_items);
    add('Cited evidence', a.source_index.map(ref => {
      const ev = run.retrieval?.evidence.find(entry => entry.evidence.evidence_id === ref.evidence_id)?.evidence;
      return `${ref.citation} · ${readable(ev?.content_kind ?? 'source')}\n  ${displayText(ev?.text ?? 'Evidence unavailable')}${ev?.workbook_notes?.length ? `\n  Source notes: ${ev.workbook_notes.map(n => displayText(n.text)).join(' ')}` : ''}`;
    }));
  } else {
    lines.push('', 'Incomplete run — no technical assessment was produced.');
    add('Validated customer facts', run.facts?.contexts.flatMap(c => Object.entries(c).flatMap(([field, value]) => {
      if (['context_id', 'label', 'missing_information'].includes(field) || value === null) return [];
      return (Array.isArray(value) ? value : [value]).map(item => `${scoped([c.context_id])} · ${readable(field)}: ${item}`);
    })) ?? []);
  }
  add('Customer claims and requests', run.facts?.customer_claims_and_requests.map(s => `${scoped(s.context_ids)} · ${readable(s.kind)}: ${s.text} (customer quote: “${s.input_quote}”)`) ?? []);
  add('Context-specific missing information', run.facts?.contexts.flatMap(c => c.missing_information.map(item => `${scoped([c.context_id])}: ${item}`)) ?? []);
  add('Shared customer constraints', run.facts?.shared_constraints ?? []);
  add('Missing customer information', run.facts?.missing_information ?? []);
  add('Processing errors', run.errors.map(e => `${e.stage} · ${e.code}: ${e.message}`));
  add('Scientific warnings', chemistWarnings([...run.warnings, ...(run.retrieval?.warnings ?? [])]));
  add('Evidence gaps', run.retrieval?.gaps.map(g => `${scoped(g.context_id ? [g.context_id] : [])}: ${g.message}`) ?? []);
  lines.push('', 'Initial assessment and proposed testing only. Source material does not establish experimental performance or clinical readiness.');
  return lines.join('\n');
}
