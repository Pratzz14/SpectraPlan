import { useEffect, useRef, useState } from 'react'
import { fetchEnquiries, fetchEnquiry, fetchExplainability } from '../../shared/api/api'
import type { EnquiryDetail, EnquirySummary, ExplainabilityTrace } from '../assessment/assessment'
import { readable } from '../assessment/assessment'
import { ExplainabilityPanel } from '../assessment/components/AssessmentResults'

export default function HistoryPage({ active, newEnquiry }: { active: boolean; newEnquiry: () => void }) {
  const [items, setItems] = useState<EnquirySummary[]>([])
  const [enquiryId, setEnquiryId] = useState('')
  const [detail, setDetail] = useState<EnquiryDetail | null>(null)
  const [runId, setRunId] = useState('')
  const [trace, setTrace] = useState<ExplainabilityTrace | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [listLoading, setListLoading] = useState(false)
  const [more, setMore] = useState(false)
  const [revision, setRevision] = useState(0)
  const listRequest = useRef<AbortController | null>(null)
  useEffect(() => () => listRequest.current?.abort(), [])
  useEffect(() => {
    if (!active) return
    const controller = new AbortController(); listRequest.current?.abort(); listRequest.current = controller
    setListLoading(true); setListError(null)
    void fetchEnquiries(controller.signal).then(rows => {
      if (!controller.signal.aborted) { setItems(rows); setMore(rows.length === 50) }
    }).catch(e => { if (!controller.signal.aborted) setListError(e instanceof Error ? e.message : 'History unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setListLoading(false) })
    return () => controller.abort()
  }, [active, revision])
  useEffect(() => {
    if (!active || !enquiryId) return
    const controller = new AbortController(); setDetail(null); setTrace(null); setError(null); setLoading(true)
    void fetchEnquiry(enquiryId, controller.signal).then(value => {
      if (controller.signal.aborted) return
      setDetail(value)
      setRunId(previous => value.runs.some(r => r.run_id === previous) ? previous : value.runs.at(-1)?.run_id ?? '')
    }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Enquiry unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [active, enquiryId, revision])
  useEffect(() => {
    if (!active || !detail || !runId) return
    const controller = new AbortController(); setTrace(null); setError(null); setLoading(true)
    void fetchExplainability(runId, controller.signal).then(value => { if (!controller.signal.aborted) setTrace(value) })
      .catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Run unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [active, detail, runId])
  async function loadMore() {
    const controller = new AbortController(); listRequest.current?.abort(); listRequest.current = controller
    setListLoading(true); setListError(null)
    try {
      const rows = await fetchEnquiries(controller.signal, items.length)
      if (!controller.signal.aborted) { setItems(old => [...old, ...rows]); setMore(rows.length === 50) }
    } catch (e) { if (!controller.signal.aborted) setListError(e instanceof Error ? e.message : 'History unavailable.') }
    finally { if (!controller.signal.aborted) setListLoading(false) }
  }
  return <div className="history-page">
    <header className="history-heading"><div><h1>History</h1><p className="section-note">Previous customer enquiries and their analysis records</p></div><div className="history-actions"><button type="button" className="secondary-button" onClick={() => setRevision(v => v + 1)}>Refresh history</button><button type="button" className="primary-button" onClick={newEnquiry}>New enquiry</button></div></header>
    <div className="split-workspace history-workspace">
      <aside className="workspace-rail history-rail" aria-label="Previous enquiries">
        <div className="history-list">{items.map(item => <button type="button" className="history-entry" key={item.enquiry_id} aria-pressed={enquiryId === item.enquiry_id} onClick={() => setEnquiryId(item.enquiry_id)}><strong>{item.original_description}</strong><span>{new Date(item.updated_at).toLocaleString()} · {item.rounds} {item.rounds === 1 ? 'round' : 'rounds'}</span></button>)}
          {listLoading ? <p role="status" className="section-note">Loading enquiries…</p> : null}
          {!listLoading && !items.length && !listError ? <p className="section-note">No enquiries have been analysed yet.</p> : null}
          {listError ? <p role="alert">{listError}</p> : null}
          {more ? <button className="secondary-button" type="button" disabled={listLoading} onClick={() => void loadMore()}>Load older enquiries</button> : null}
        </div>
      </aside>
      <section className="workspace-results history-results" aria-label="Saved enquiry details" aria-busy={loading}>
        {detail ? <div className="history-run-controls"><label>Analysis round<select aria-label="Analysis round" value={runId} onChange={event => setRunId(event.target.value)}>{detail.runs.map(run => <option key={run.run_id} value={run.run_id}>Round {run.round_no} · {readable(run.status)} · {new Date(run.created_at).toLocaleString()}</option>)}</select></label><a className="secondary-button" href={`#assess?run=${encodeURIComponent(runId)}`}>Continue in Assessment</a></div> : null}
        {error ? <p role="alert" className="error-panel">{error} <button type="button" onClick={() => setRevision(v => v + 1)}>Retry</button></p> : null}
        {loading ? <p role="status" className="section-note">Loading saved analysis…</p> : null}
        {trace ? <><div className="history-outcome"><h2>{trace.run?.assessment ? readable(trace.run.assessment.decision_status) : readable(trace.status)}</h2>{trace.run?.assessment ? <p>{trace.run.assessment.case_summary}</p> : null}<a className="secondary-button" href={`/api/assess/${trace.run_id}/report.pdf?audience=trace`} download>Download trace PDF</a></div><ExplainabilityPanel key={trace.run_id} trace={trace} /></> : !enquiryId ? <div className="empty-workspace"><h2>Select a previous enquiry</h2><p>Review its submitted query, clarification answers, searches, source files and model responses.</p></div> : null}
      </section>
    </div>
  </div>
}
