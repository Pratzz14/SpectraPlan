import { useState } from 'react'
import type { ReactNode } from 'react'
import { chemistWarnings, clarificationKey, compactRequirements, contextLabel, displayText, readable, requirementLabel, uniqueDisplayItems, usefulClarificationReason } from '../assessment'
import type { Assessment, AssessmentRun, Assertion, CaseFacts, ClarificationQuestion, ExplainabilityTrace, Experiment, Recommendation, Requirement } from '../assessment'

export type InspectEvidence = (id: string, claim: string) => void
export interface CitationProps { run: AssessmentRun; inspect: InspectEvidence }

export function CitationButtons({ ids, claim, run, inspect }: CitationProps & { ids: string[]; claim: string }) {
  return <span className="citation-group">{[...new Set(ids)].map(id => {
    const reference = run.assessment?.source_index.find(ref => ref.evidence_id === id)
    return <button key={id} type="button" className="citation" onClick={() => inspect(id, claim)} aria-label={`Inspect evidence ${reference?.citation ?? 'source'} for ${displayText(claim)}`}>{reference?.citation ?? 'Source'}</button>
  })}</span>
}

export function Claim({ claim, run, inspect }: CitationProps & { claim: Assertion }) {
  return <div className="claim"><p>{displayText(claim.text.replace(/^Source excerpt \([^)]+\):\s*/, ''))}</p><CitationButtons ids={claim.evidence_ids} claim={claim.text} run={run} inspect={inspect} /></div>
}

function TextList({ title, items }: { title: string; items: string[] }) {
  const cleanItems = uniqueDisplayItems(items)
  return cleanItems.length ? <div className="result-block"><h3>{title}</h3><ul className="result-list">{cleanItems.map((item, i) => <li key={i}>{item}</li>)}</ul></div> : null
}

export function Panel({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  return <section className={`result-panel ${className}`} aria-label={title}><h2>{title}</h2>{children}</section>
}

function requirementRows(facts: CaseFacts | null, requirements: Requirement[] | undefined, contextId: string | null) {
  if (requirements) return requirements.filter(r => r.context_id === contextId)
  const context = facts?.contexts.find(c => c.context_id === contextId)
  if (!context) return []
  // For incomplete runs, render only validated extracted values and their input provenance.
  const index = facts?.contexts.indexOf(context) ?? -1
  return Object.entries(context).flatMap(([field, value]) => {
    if (['context_id', 'label', 'missing_information', 'response_time_s'].includes(field) || value === null) return []
    const entries = Array.isArray(value) ? value : [value]
    return entries.map((item, i) => {
      const path = `/contexts/${index}/${field}${Array.isArray(value) ? `/${i}` : ''}`
      return { context_id: contextId, field, field_path: path, value: String(item), origin: 'customer' as const, input_quote: facts?.fact_provenance.find(p => p.field_path === path)?.input_quote ?? '' }
    })
  })
}

export function RequirementsPanel({ run }: { run: AssessmentRun }) {
  const facts = run.facts
  const requirements = run.assessment?.requirements
  const contexts = [...(facts?.contexts.map(c => ({ id: c.context_id, label: contextLabel(facts, [c.context_id]) })) ?? []), { id: null, label: 'Shared requirements' }]
  const contextMissing = new Set(facts?.contexts.flatMap(c => c.missing_information.map(value => value.trim().toLowerCase())) ?? [])
  const missing = [...new Set([...(requirements?.unknowns ?? []), ...(facts?.missing_information ?? [])])].filter(value => !contextMissing.has(value.trim().toLowerCase()))
  return <Panel title="Process requirements">
    {contexts.map(c => {
      const rows = requirementRows(facts, requirements?.stated, c.id)
      const summary = compactRequirements(rows, c.label)
      const unknowns = facts?.contexts.find(context => context.context_id === c.id)?.missing_information ?? []
      return rows.length || unknowns.length ? <section className="context-section" key={c.id ?? 'shared'} aria-label={`${c.label} requirements`}>
        <h3>{c.label}</h3>
        {summary.length ? <dl className="requirement-summary">{summary.map(row => <div key={row.label}><dt>{row.label}</dt><dd>{row.values.join(' · ')}</dd></div>)}</dl> : rows.length ? <p className="section-note">No further process details were provided.</p> : null}
        {unknowns.length ? <details className="missing-details"><summary>Missing information for this stream ({unknowns.length})</summary><ul className="result-list">{uniqueDisplayItems(unknowns).map((item, i) => <li key={i}>{item}</li>)}</ul></details> : null}
      </section> : null
    })}
    {!facts ? <p>No validated customer facts are available yet.</p> : null}
    <TextList title="Shared customer constraints" items={facts?.shared_constraints ?? []} />
    {missing.length ? <details className="missing-details"><summary>Other missing information ({missing.length})</summary><ul className="result-list">{uniqueDisplayItems(missing).map((item, i) => <li key={i}>{item}</li>)}</ul></details> : null}
    {facts ? <details className="extraction-review"><summary>Review extracted details and original wording</summary><p className="section-note">Extracted from your enquiry. Customer claims and proposed approaches remain attributed to you.</p>
      {contexts.map(c => {
        const rows = requirementRows(facts, requirements?.stated, c.id)
        return rows.length ? <section key={c.id ?? 'shared'}><h3>{c.label}</h3><dl className="fact-list">{rows.map((r, i) => <div key={`${r.field_path}-${i}`}><dt>{requirementLabel(r.field)}</dt><dd>{r.value}{r.input_quote ? <blockquote>{r.input_quote}</blockquote> : null}</dd></div>)}</dl></section> : null
      })}
      {facts.customer_claims_and_requests.length ? <div className="result-block"><h3>Customer claims and requests</h3>{facts.customer_claims_and_requests.map((s, i) => <div className="customer-statement" key={i}><p className="eyebrow">{readable(s.kind)} · {contextLabel(facts, s.context_ids)}</p><p>{displayText(s.text)}</p><blockquote>{displayText(s.input_quote)}</blockquote></div>)}</div> : null}
    </details> : null}
  </Panel>
}

function grouped<T extends { context_ids: string[] }>(items: T[], facts: CaseFacts | null): { label: string; items: T[] }[] {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const key = [...new Set(item.context_ids)].sort().join('|')
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  return Array.from(groups.values(), group => ({ label: contextLabel(facts, group[0].context_ids), items: group }))
}

export function ClarificationList({ questions, run, inspect, answers, answer }: CitationProps & { questions: ClarificationQuestion[]; answers?: Record<string, { answer: string }>; answer?: (question: ClarificationQuestion, text: string) => void }) {
  return <Panel title="Clarification questions">
    {questions.length ? grouped([...questions].sort((a, b) => a.priority - b.priority), run.facts).map(group => <section className="context-section" key={group.label}>{run.facts && run.facts.contexts.length > 1 ? <h3>{group.label}</h3> : null}<ol className="question-list">{group.items.map(q => <li key={clarificationKey(q)}><span className="question-number" aria-label={`Priority ${q.priority}`}>{q.priority}</span><div className="question-content"><h4>{q.question}</h4>{usefulClarificationReason(q) ? <Claim claim={q.reason} run={run} inspect={inspect} /> : null}{q.affects.length ? <p className="section-note">Affects: {q.affects.map(readable).join(', ')}</p> : null}{answer ? <textarea aria-label={`Answer: ${q.question}`} rows={2} placeholder="Add your answer…" value={answers?.[clarificationKey(q)]?.answer ?? ''} onChange={event => answer(q, event.target.value)} /> : null}</div></li>)}</ol></section>) : <p className="section-note">No further questions.</p>}
  </Panel>
}

function JsonBlock({ value }: { value: unknown }) {
  const [visible, setVisible] = useState(false)
  return <details className="trace-json" onToggle={event => setVisible(event.currentTarget.open)}><summary>Inspect event payload</summary>{visible ? <pre>{JSON.stringify(value, null, 2)}</pre> : null}</details>
}

export function ExplainabilityPanel({ trace }: { trace: ExplainabilityTrace }) {
  const [exportError, setExportError] = useState<string | null>(null)
  function downloadTrace() {
    try {
      const url = URL.createObjectURL(new Blob([JSON.stringify(trace, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a'); link.href = url; link.download = `spectraplan-trace-${trace.run_id}.json`
      document.body.append(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setExportError(null)
    } catch { setExportError('Trace download could not start. Please try again.') }
  }
  const retrievalQueries = trace.run?.retrieval?.queries ?? []
  const evidence = trace.run?.retrieval?.evidence ?? []
  const providerEvents = trace.events.filter(event => event.event_type === 'provider_request')
  return <Panel title="Explainability">
    <p className="section-note">Stored chronological trace for run {trace.run_id}. Status: {trace.status}. Completed events remain available if processing was interrupted.</p>
    <button type="button" className="secondary-button" onClick={downloadTrace}>Download trace JSON</button>
    {exportError ? <p role="alert">{exportError}</p> : null}
    {trace.legacy_run ? <div className="result-block"><h3>Original saved result</h3><p>This result uses an older format. Its original data is preserved below.</p><JsonBlock value={trace.legacy_run} /></div> : null}
    <div className="result-block">
      <h3>Customer input</h3>
      <blockquote>{trace.description}</blockquote>
      {trace.clarification_answers.length ? <><h4>Clarification answers</h4><ul className="result-list">{trace.clarification_answers.map((item, i) => <li key={i}><strong>{item.question}</strong><br />{item.answer}</li>)}</ul></> : <p className="section-note">No clarification answers were submitted.</p>}
    </div>
    <div className="result-block">
      <h3>Retrieval path</h3>
      <p>{retrievalQueries.length} generated queries · {new Set(evidence.map(item => item.evidence.source_id)).size} selected source files · {evidence.length} passages · {trace.run?.retrieval?.ranking ?? 'No retrieval result'}</p>
      {retrievalQueries.length ? <details><summary>Queries, terms, candidates, and scores</summary><div className="trace-list">{retrievalQueries.map(query => <div className="trace-item" key={query.query_id}><strong>{query.facet} · {query.context_id}</strong><p>{query.query}</p><p className="section-note">Expanded: {query.expanded_terms.join(', ') || 'none'} · Omitted: {query.omitted_terms.join(', ') || 'none'} · Candidates: {query.candidates.length}</p><JsonBlock value={query} /></div>)}</div></details> : null}
      {evidence.length ? <details><summary>Fetched evidence files</summary><ul className="result-list">{evidence.map(item => <li key={item.evidence.evidence_id}><strong>{item.evidence.file_name}</strong> · {item.evidence.evidence_id}<br />{item.evidence.section}</li>)}</ul></details> : null}
    </div>
    <div className="result-block">
      <h3>Model and validation stages</h3>
      <p>{providerEvents.length} provider calls recorded · {trace.run?.metadata.provider} · {trace.run?.metadata.model}</p>
      <div className="trace-list">{trace.events.map(event => <div className="trace-item" key={`${event.sequence}-${event.event_type}`}><strong>{event.stage} · {event.event_type}</strong><span className="section-note"> · {event.created_at}</span><JsonBlock value={event.payload} /></div>)}</div>
    </div>
  </Panel>
}

function MethodCard({ recommendation: r, run, inspect }: CitationProps & { recommendation: Recommendation }) {
  return <article className="method-card">
    <div className="card-heading"><h4>{displayText(r.method)}</h4><span className="badge">{readable(r.status)}</span></div>
    <Claim claim={r.rationale} run={run} inspect={inspect} />
    <dl className="concept-grid"><div><dt>Geometry</dt><dd>{displayText(r.geometry ?? 'Unknown — requires clarification')}</dd><dt className="location-label">Measurement location</dt><dd>{displayText(r.measurement_location ?? 'Unknown — requires clarification')}</dd></div><div><dt>Spectral coverage · {readable(r.spectral_range.kind)}</dt><dd>{displayText(r.spectral_range.interval ?? 'Not yet established')}</dd><CitationButtons ids={r.spectral_range.evidence_ids} claim={r.spectral_range.text} run={run} inspect={inspect} /></div></dl>
    {r.spectral_range.raman_excitation ? <div className="result-block"><h5>Raman excitation wavelength</h5><Claim claim={r.spectral_range.raman_excitation} run={run} inspect={inspect} /></div> : null}
    {r.spectral_range.raman_shift ? <div className="result-block"><h5>Raman shift coverage</h5><Claim claim={r.spectral_range.raman_shift} run={run} inspect={inspect} /></div> : null}
    <details className="method-details"><summary>Range qualification, assumptions and limitations</summary><Claim claim={r.spectral_range} run={run} inspect={inspect} />{r.spectral_range.kind === 'nominal_method_range' ? <p className="section-note">Nominal method coverage is not a verified instrument, fiber or probe specification.</p> : null}<TextList title="Assumptions — not stated facts" items={r.assumptions} />{r.limitations.length ? <div className="result-block"><h5>Limitations</h5>{r.limitations.map((claim, i) => <Claim key={i} claim={claim} run={run} inspect={inspect} />)}</div> : null}</details>
  </article>
}

export function RecommendationCards({ assessment, run, inspect }: CitationProps & { assessment: Assessment }) {
  return <Panel title="Method shortlist">
    {assessment.recommendations.length ? grouped(assessment.recommendations, run.facts).map(group => <section className="context-section" key={group.label}><h3>{group.label}</h3>{group.items.map((r, i) => <MethodCard key={i} recommendation={r} run={run} inspect={inspect} />)}</section>) : <div className="empty-shortlist"><h3>No supported method shortlist</h3><p>{assessment.decision_reason}</p><p>Resolve the clarification questions and follow the proposed investigation before selecting a method or configuration.</p></div>}
  </Panel>
}

export function ExperimentPlan({ experiment: e, facts }: { experiment: Experiment; facts: CaseFacts | null }) {
  return <Panel title="First feasibility experiment">
    <p className="eyebrow">Proposed study · {contextLabel(facts, e.context_ids)}</p><p>{e.objective}</p>
    <TextList title="Samples" items={e.samples} /><TextList title="Measurements and reference assays" items={e.measurements} /><TextList title="Methods to compare" items={e.comparisons} /><TextList title="Variation to cover" items={e.variation} />
    <div className="result-block"><h3>Independent validation</h3><p>{e.validation}</p>{e.validation_groups.map((g, i) => <p key={i} className="validation-group"><strong>{contextLabel(facts, g.context_ids)}</strong> · {readable(g.study_type)} · Independent unit: {g.independent_unit}</p>)}</div>
    <TextList title="Proposed settings — not requirements or measured results" items={e.proposed_settings.map(s => `${contextLabel(facts, s.context_ids)} · ${displayText(s.name)}: ${s.value}${s.unit ? ` ${s.unit}` : ''}`)} />
    {e.acceptance_criteria.length ? <div className="result-block"><h3>Acceptance criteria</h3><ul className="result-list">{e.acceptance_criteria.map((c, i) => <li key={i}><strong>{contextLabel(facts, [c.context_id])} · {readable(c.metric)}:</strong> {c.threshold ?? 'Unknown — agree with customer'} <span className="section-note">({c.origin === 'customer' ? 'Customer requirement' : 'Unspecified'})</span></li>)}</ul></div> : null}
    <div className="result-block"><h3>Go / no-go decision</h3><p>{e.decision_criteria}</p></div><TextList title="Open items" items={e.open_items} />
  </Panel>
}

export function RunNotes({ run, inspect, section = 'all' }: CitationProps & { section?: 'all' | 'risks' | 'warnings' }) {
  const warnings = chemistWarnings([...run.warnings, ...(run.retrieval?.warnings ?? [])])
  return <>
    {section !== 'warnings' && run.assessment?.risks.length ? <Panel title="Risks and limitations">{grouped(run.assessment.risks, run.facts).map(group => <section className="context-section" key={group.label}><h3>{group.label}</h3>{group.items.map((claim, i) => <Claim key={i} claim={claim} run={run} inspect={inspect} />)}</section>)}</Panel> : null}
    {section !== 'risks' && (warnings.length || run.retrieval?.gaps.length) ? <Panel title="Warnings and evidence gaps"><TextList title="Scientific warnings" items={warnings} />{run.retrieval?.gaps.map((gap, i) => <div className="result-block" key={i}><h3>{contextLabel(run.facts, gap.context_id ? [gap.context_id] : [])}{gap.facet ? ` · ${readable(gap.facet)}` : ''}</h3><p>{displayText(gap.message)}</p></div>)}</Panel> : null}
  </>
}
