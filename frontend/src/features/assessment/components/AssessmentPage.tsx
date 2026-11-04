import { evidenceLocation } from '../evidenceLocation'
import { useEffect, useRef, useState } from 'react'
import { assessEnquiry, fetchSavedAssessment, fetchEnquiry, waitForAssessment } from '../../../shared/api/api'
import { chemistWarnings, clarificationKey, composeEnquiry, contextLabel, readable } from '../assessment'
import type { AssessmentRun, ClarificationAnswer, ClarificationQuestion } from '../assessment'
import CustomerInput from './CustomerInput'
import ActionBar from './ActionBar'
import EvidenceDrawer from './EvidenceDrawer'
import Accordion from '../../../shared/ui/Accordion'
import { ClarificationList, ExperimentPlan, RecommendationCards, RequirementsPanel, RunNotes } from './AssessmentResults'

const progressLabels: Record<string,string> = {queued:'Queued — waiting for processing…',extraction:'Reading your requirements…',retrieval:'Searching the published evidence…',synthesis:'Preparing your assessment…'}

export default function AssessmentPage({ initialRun = '', newEnquiry }: { initialRun?: string; newEnquiry: () => void }) {
  const [draft, setDraft] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [run, setRun] = useState<AssessmentRun | null>(null)
  const [questionRun, setQuestionRun] = useState<AssessmentRun | null>(null)
  const [answers, setAnswers] = useState<Record<string, ClarificationAnswer>>({})
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState('Preparing assessment…')
  const [restoring, setRestoring] = useState(!!initialRun)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<{ id: string; claim: string; source: AssessmentRun } | null>(null)
  const [enquiryId, setEnquiryId] = useState<string | undefined>()
  const [currentRunId, setCurrentRunId] = useState<string | undefined>()
  const active = useRef<AbortController | null>(null)
  const resultHeading = useRef<HTMLHeadingElement>(null)
  const questions = questionRun?.assessment?.clarification_questions ?? []
  const description = composeEnquiry(draft, Object.values(answers))
  const changed = !!submitted && description !== submitted
  const previousAnswers = Object.entries(answers).filter(([key]) => !questions.some(q => clarificationKey(q) === key))
  useEffect(() => () => { active.current?.abort(); active.current = null }, [])
  async function submit() {
    if (restoring || !draft.trim()) return
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    setSubmitted(description); setRun(null); setSelected(null); setError(null); setLoading(true)
    try {
      const result = await assessEnquiry({ description: draft, enquiry_id: enquiryId, parent_run_id: currentRunId, clarification_answers: Object.values(answers).filter(item => item.answer.trim()) }, controller.signal, setProgress)
      if (active.current === controller && !controller.signal.aborted) {
        if (['', '#assess'].includes(window.location.hash.split('?')[0])) {
          window.history.replaceState(null, '', `#assess?run=${encodeURIComponent(result.metadata.run_id)}`)
        }
        setRun(result)
        setEnquiryId(result.metadata.enquiry_id ?? undefined); setCurrentRunId(result.metadata.run_id)
        if (result.assessment) setQuestionRun(result)

      }
    } catch (failure) {
      if (active.current === controller && !controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'The assessment failed. Please try again.')
    } finally { if (active.current === controller && !controller.signal.aborted) setLoading(false) }
  }
  async function openRun(runId: string) {
    active.current?.abort()
    const controller = new AbortController(); active.current = controller
    setRestoring(true); setLoading(true); setError(null); setSelected(null)
    setDraft(''); setSubmitted(''); setRun(null); setQuestionRun(null); setAnswers({})
    setEnquiryId(undefined); setCurrentRunId(undefined)
    try {
      let saved = await fetchSavedAssessment(runId, controller.signal)
      setDraft(saved.draft_description); setSubmitted(saved.description)
      setEnquiryId(saved.enquiry_id); setCurrentRunId(saved.run_id)
      const restoredAnswers: Record<string, ClarificationAnswer> = {}
      for (const a of saved.clarification_answers) restoredAnswers[JSON.stringify([a.origin_run_id, a.question_id, a.context, a.question])] = a
      setAnswers(restoredAnswers)
      if (['queued', 'running'].includes(saved.status)) {
        await waitForAssessment(runId, controller.signal, setProgress)
        saved = await fetchSavedAssessment(runId, controller.signal)
      }
      let questions = saved.run
      if (!questions?.assessment) {
        const detail = await fetchEnquiry(saved.enquiry_id, controller.signal)
        const byId = new Map(detail.runs.map(r => [r.run_id, r]))
        let parent = saved.parent_run_id
        while (parent && !questions?.assessment) {
          const previous = await fetchSavedAssessment(parent, controller.signal)
          questions = previous.run; parent = byId.get(parent)?.parent_run_id ?? null
        }
      }
      if (active.current !== controller || controller.signal.aborted) return
      setDraft(saved.draft_description); setSubmitted(saved.description); setRun(saved.run); setQuestionRun(questions?.assessment ? questions : null)
      // Match saved answers to the original context IDs rather than their display labels.
      const restored: Record<string, ClarificationAnswer> = {}
      for (const a of saved.clarification_answers) {
        const question = questions?.assessment?.clarification_questions.find((q, index) =>
          (a.origin_run_id === questions?.metadata.run_id && a.question_id === questions?.metadata.question_ids?.[index])
          || (a.question === q.question && a.context === contextLabel(questions?.facts ?? null, q.context_ids)))
        restored[question ? clarificationKey(question) : JSON.stringify([a.origin_run_id, a.question_id, a.context, a.question])] = a
      }
      setAnswers(restored); setEnquiryId(saved.enquiry_id); setCurrentRunId(saved.run_id)
      if (saved.status === 'interrupted' || saved.status === 'running') setError(`This analysis is ${saved.status}. Its recorded events are available; you can analyze again.`)
    } catch (failure) {
      if (active.current === controller && !controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Saved enquiry could not be opened.')
    } finally {
      if (active.current === controller && !controller.signal.aborted) {
        setLoading(false); setRestoring(false)
      }
    }
  }
  useEffect(() => { if (initialRun) void openRun(initialRun) }, [initialRun])
  useEffect(() => { if (run || error) resultHeading.current?.focus() }, [run, error])
  const inspect = (id: string, claim: string) => { if (run) setSelected({ id, claim, source: run }) }
  const inspectQuestion = (id: string, claim: string) => { if (questionRun) setSelected({ id, claim, source: questionRun }) }
  const evidence = selected?.source.retrieval?.evidence.find(entry => entry.evidence.evidence_id === selected.id)?.evidence
  function answer(question: ClarificationQuestion, text: string) {
    const index = questionRun?.assessment?.clarification_questions.findIndex(q => clarificationKey(q) === clarificationKey(question)) ?? -1
    const qid = questionRun?.metadata.question_ids?.[index]
    setAnswers(current => ({ ...current, [clarificationKey(question)]: { question: question.question, context: contextLabel(questionRun?.facts ?? null, question.context_ids), answer: text, question_id: qid, origin_run_id: qid ? questionRun?.metadata.run_id : undefined } }))
  }
  const warnings = chemistWarnings([...(run?.warnings ?? []), ...(run?.retrieval?.warnings ?? [])])
  const gaps = run?.retrieval?.gaps ?? []
  const assessment = run?.assessment
  const status = assessment ? assessment.decision_status === 'provisional'
    ? assessment.recommendations.some(r => r.status === 'conditional_on_clarification') ? 'Conditional' : 'Provisional'
    : readable(assessment.decision_status) : undefined
  function goToSection(id: string) {
    const section = document.getElementById(id)
    if (section instanceof HTMLDetailsElement) section.open = true
    section?.scrollIntoView({ block: 'start' })
  }
  const sourceCount = new Set(run?.retrieval?.evidence.map(entry => entry.evidence.source_id) ?? []).size
  const requirementSummary = run?.facts?.contexts.map(c => [...c.target_analytes, c.sample_matrix ?? c.label].join(' · ')).join(' / ')
  return <div className="assessment-page"><div className="split-workspace assessment-workspace">
    <form className="workspace-rail enquiry-rail" onSubmit={event => { event.preventDefault(); void submit() }}>
      <CustomerInput draft={draft} change={setDraft} />
      <div className="questions-scroll">
        {questionRun ? <ClarificationList questions={questions} run={questionRun} inspect={inspectQuestion} answers={answers} answer={answer} /> : <section className="pending-questions"><h2>Clarification questions</h2><p className="section-note">{loading ? 'Preparing questions…' : 'Questions will appear after analysis.'}</p></section>}
        {previousAnswers.length ? <details className="previous-answers"><summary>Previous answers ({previousAnswers.length})</summary>{previousAnswers.map(([key, item]) => <label key={key}>{item.question}<textarea rows={2} value={item.answer} onChange={event => setAnswers(current => ({ ...current, [key]: { ...item, answer: event.target.value } }))} /></label>)}</details> : null}
      </div>
      <div className="rail-actions"><button className="primary-button" type="submit" disabled={restoring || !draft.trim() || (loading && !changed)}>{restoring ? 'Loading saved enquiry…' : loading ? changed ? 'Analyze updated enquiry' : 'Analyzing…' : submitted ? 'Analyze again' : 'Analyze'}</button><button type="button" className="secondary-button new-enquiry-button" onClick={newEnquiry}>New enquiry</button><p className="section-note">{changed ? 'Changes not analyzed' : 'Submit enquiry and answers together.'}</p></div>
    </form>
    <section className="workspace-results assessment-output" aria-label="Assessment results" aria-busy={loading}>
      <div className="result-scroll">
        <div role="status" aria-live="polite">{loading ? <p className="compact-notice"><span className="loading-dot" />Analyzing enquiry and supporting evidence…</p> : null}</div>
        {error ? <div role="alert" className="error-panel"><h2 ref={resultHeading} tabIndex={-1}>Assessment could not be completed</h2><p>{error}</p></div> : null}
        {run?.run_status === 'incomplete' ? <div className="error-panel" role="alert"><h2 ref={resultHeading} tabIndex={-1}>No technical assessment produced</h2>{run.errors.map(failure => <p key={failure.code}><strong>{failure.stage} · {failure.code}</strong><br />{failure.message}</p>)}<p>Validated partial results remain available below.</p></div> : null}
        {!run && !loading && !error ? <div className="assessment-empty"><h2 ref={resultHeading} tabIndex={-1}>Your technical assessment starts here.</h2><p>Describe what you want to measure, how your process works, and the constraints that matter.</p><ol><li><strong>Understand the enquiry</strong><span>Review the requirements and answer any clarification questions.</span></li><li><strong>Explore supported methods</strong><span>Read the assessment alongside its source evidence.</span></li><li><strong>Plan a first experiment</strong><span>Identify samples, reference measurements, and the decisions to test.</span></li></ol></div> : null}
        {assessment ? <header id="assessment-overview" className="assessment-report-header"><div className="assessment-report-title"><h2>Technical assessment</h2><span className="report-status">{status}</span></div><p className="report-source-note">{sourceCount} source {sourceCount === 1 ? 'document' : 'documents'} consulted · Preliminary assessment</p><p className="report-lead">{assessment.decision_reason}</p></header> : null}
        {run ? <nav className="report-navigation" aria-label="Assessment sections"><a href="#assessment-overview" onClick={event => { event.preventDefault(); goToSection('assessment-overview') }}>Overview</a><a href="#assessment-methods" onClick={event => { event.preventDefault(); goToSection('assessment-methods') }}>Methods</a><a href="#assessment-requirements" onClick={event => { event.preventDefault(); goToSection('assessment-requirements') }}>Requirements</a><a href="#assessment-experiment" onClick={event => { event.preventDefault(); goToSection('assessment-experiment') }}>Experiment</a><a href="#assessment-risks" onClick={event => { event.preventDefault(); goToSection('assessment-risks') }}>Risks</a></nav> : null}
        {run ? <div key={run.metadata.run_id} className="assessment-sections">
          <Accordion id="assessment-methods" title="Method shortlist" description={assessment && assessment.recommendations.length > 1 ? `${assessment.recommendations.length} methods` : undefined} status={status} open headingRef={assessment || !run ? resultHeading : undefined}>
            {assessment ? <><RecommendationCards assessment={assessment} run={run} inspect={inspect} /></> : <p className="section-note" aria-live="polite">{run ? 'No validated recommendations are available.' : loading ? progressLabels[progress] ?? 'Preparing assessment…' : 'Enter an enquiry to compare supported methods.'}</p>}
          </Accordion>
          <Accordion id="assessment-requirements" title="Process requirements" description={requirementSummary || 'Requirements and constraints'} open>{run ? <RequirementsPanel run={run} /> : <p className="section-note">Analyze an enquiry to extract its requirements.</p>}</Accordion>
          <Accordion id="assessment-experiment" title="First feasibility experiment" description="Samples, reference measurements and validation" open>{assessment ? <ExperimentPlan experiment={assessment.experiment} facts={run.facts} /> : <p className="section-note">No experiment has been produced yet.</p>}</Accordion>
          <Accordion id="assessment-risks" open title="Risks and limitations" description={assessment?.risks.length ? `${assessment.risks.length} assessment risks and method-specific limitations` : assessment ? 'No additional risks returned' : 'Suitability and validation limits'}>{run ? <RunNotes run={run} inspect={inspect} section="risks" /> : null}</Accordion>
          <Accordion title="Warnings and evidence gaps" description={warnings[0] ?? gaps[0]?.message ?? (run ? 'No processing warnings or retrieval gaps' : 'Coverage and evidence status')} warning={!!(warnings.length || gaps.length)}>{run ? <RunNotes run={run} inspect={inspect} section="warnings" /> : null}</Accordion>
          {run?.run_status === 'incomplete' && run.retrieval?.evidence.length ? <Accordion title="Retrieved evidence" description="Candidates available before failure">{run.retrieval.evidence.map(entry => <button className="citation" type="button" key={entry.evidence.evidence_id} onClick={() => inspect(entry.evidence.evidence_id, 'Retrieved candidate — no final assessment was produced.')}>{evidenceLocation(entry.evidence)}</button>)}</Accordion> : null}
        </div> : null}
        {run ? <details className="run-metadata"><summary>Submitted enquiry</summary><p className="submitted-text">{submitted}</p></details> : null}
      </div>
      {run ? <ActionBar run={run} description={submitted} loading={loading} compact /> : null}
    </section>
    {selected && evidence ? <EvidenceDrawer key={`${selected.source.metadata.run_id}:${selected.id}`} evidence={evidence} claim={selected.claim} close={() => setSelected(null)} /> : null}
  </div></div>
}
