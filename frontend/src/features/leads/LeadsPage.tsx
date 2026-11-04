import './leads.css'
import { ProtectedFile } from '../../shared/ui/ProtectedMedia'
import { useEffect, useRef, useState } from 'react'
import { fetchEnquiries, fetchEnquiry, fetchExplainability } from '../../shared/api/api'
import type { EnquiryDetail, EnquirySummary, ExplainabilityTrace } from '../assessment/assessment'
import { readable } from '../assessment/assessment'
import { ExplainabilityPanel } from '../assessment/components/AssessmentResults'

export default function LeadsPage({ active, newEnquiry }: { active: boolean; newEnquiry: () => void }) {
  const [email, setEmail] = useState('')
  const [filter, setFilter] = useState('')
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
    void fetchEnquiries(controller.signal, 0, filter).then(rows => {
      if (!controller.signal.aborted) { setItems(rows); setMore(rows.length === 50) }
    }).catch(e => { if (!controller.signal.aborted) setListError(e instanceof Error ? e.message : 'Leads unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setListLoading(false) })
    return () => controller.abort()
  }, [active, revision, filter])
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
  function applyFilter(value: string) {
    setFilter(value.trim())
    setItems([]); setMore(false); setEnquiryId(''); setDetail(null); setTrace(null)
    setRevision(current => current + 1)
  }
  async function loadMore() {
    const controller = new AbortController(); listRequest.current?.abort(); listRequest.current = controller
    setListLoading(true); setListError(null)
    try {
      const rows = await fetchEnquiries(controller.signal, items.length, filter)
      if (!controller.signal.aborted) { setItems(old => [...old, ...rows]); setMore(rows.length === 50) }
    } catch (e) { if (!controller.signal.aborted) setListError(e instanceof Error ? e.message : 'Leads unavailable.') }
    finally { if (!controller.signal.aborted) setListLoading(false) }
  }
  return <div className="history-page">
    <header className="history-heading">
      <form className="lead-filter" onSubmit={event => { event.preventDefault(); applyFilter(email) }}>
        <label htmlFor="lead-email">Filter by email
          <input id="lead-email" type="search" placeholder="Customer email" maxLength={320} value={email} onChange={event => setEmail(event.target.value)} />
        </label>
        <button className="secondary-button" type="submit">Filter</button>
        <button className="secondary-button" type="button" onClick={() => { setEmail(''); applyFilter('') }}>Clear</button>
      </form>
    <section className="leads-overview" aria-label="Enquiry activity">
      <div className="leads-metrics">
        <div><span>Enquiries shown</span><strong>{listLoading && !items.length ? '—' : items.length}</strong></div>
        <div><span>Updated in last 7 days</span><strong>{listLoading && !items.length ? '—' : items.filter(item => { const time = Date.parse(item.updated_at); return time <= Date.now() && time >= Date.now() - 7 * 86400000 }).length}</strong></div>
      </div>
      <p className="section-note">Based on loaded enquiries{filter ? ' matching the email filter' : ''}{more ? ' · Load older enquiries to include more activity' : ''}</p>
    </section>
      <div className="history-actions">
        <button type="button" className="secondary-button" onClick={() => setRevision(value => value + 1)}>Refresh leads</button>
        <button type="button" className="primary-button" onClick={newEnquiry}>New enquiry</button>
      </div>
    </header>
    {!items.length && !enquiryId ? <section className="leads-empty" aria-live="polite">
      {listLoading ? <><h2>Loading customer enquiries…</h2><p>Your saved enquiries will appear here.</p></> : listError ? <><h2>Could not load enquiries</h2><p role="alert">{listError}</p><button className="secondary-button" type="button" onClick={() => setRevision(v => v + 1)}>Try again</button></> : <>
        <span className="leads-empty-label">CUSTOMER ENQUIRIES</span>
        <h2>{filter ? 'No enquiries match this email' : 'Your enquiry inbox is ready'}</h2>
        <p>{filter ? 'Try another email address or clear the filter to see all enquiries.' : 'Run an assessment to save your first enquiry. You can then review the customer’s request, analysis rounds and follow-up answers here.'}</p>
        {filter ? <button className="secondary-button" type="button" onClick={() => { setEmail(''); applyFilter('') }}>Show all enquiries</button> : <button className="primary-button" type="button" onClick={newEnquiry}>Create first enquiry</button>}
      </>}
    </section> : <div className="split-workspace history-workspace">
      <aside className="workspace-rail history-rail" aria-label="Previous enquiries">
        <div className="leads-list-heading"><h2>Customer enquiries</h2><p className="section-note">Newest activity first</p></div><div className="history-list">{items.map(item => <button type="button" className="history-entry" key={item.enquiry_id} aria-pressed={enquiryId === item.enquiry_id} onClick={() => setEnquiryId(item.enquiry_id)}><strong>{item.customer_email || 'Legacy — email unavailable'}</strong><span>{item.original_description}</span><span>{new Date(item.updated_at).toLocaleString()} · {item.rounds} {item.rounds === 1 ? 'round' : 'rounds'}</span></button>)}
          {listLoading ? <p role="status" className="section-note">Loading enquiries…</p> : null}
          {!listLoading && !items.length && !listError ? <p className="section-note">{filter ? 'No leads match this email.' : 'No enquiries have been analysed yet.'}</p> : null}
          {listError ? <p role="alert">{listError}</p> : null}
          {more ? <button className="secondary-button" type="button" disabled={listLoading} onClick={() => void loadMore()}>Load older enquiries</button> : null}
        </div>
      </aside>
      <section className="workspace-results history-results" aria-label="Saved enquiry details" aria-busy={loading}>
        {detail ? <div className="history-run-controls"><p>{detail.customer_email || 'Legacy — email unavailable'}</p><label>Analysis round<select aria-label="Analysis round" value={runId} onChange={event => setRunId(event.target.value)}>{detail.runs.map(run => <option key={run.run_id} value={run.run_id}>Round {run.round_no} · {readable(run.status)} · {new Date(run.created_at).toLocaleString()}</option>)}</select></label><a className="secondary-button" href={`#assess?run=${encodeURIComponent(runId)}`}>Continue in Assessment</a></div> : null}
        {error ? <p role="alert" className="error-panel">{error} <button type="button" onClick={() => setRevision(v => v + 1)}>Retry</button></p> : null}
        {loading ? <p role="status" className="section-note">Loading saved analysis…</p> : null}
        {trace ? <><div className="history-outcome"><h2>{trace.run?.assessment ? readable(trace.run.assessment.decision_status) : readable(trace.status)}</h2>{trace.run?.assessment ? <p>{trace.run.assessment.case_summary}</p> : null}<ProtectedFile className="secondary-button" href={`/api/assess/${trace.run_id}/report.pdf?audience=trace`} download={`spectraplan-trace-${trace.run_id}.pdf`}>Download trace PDF</ProtectedFile></div><ExplainabilityPanel key={trace.run_id} trace={trace} /></> : !enquiryId ? <div className="empty-workspace"><h2>Select a previous enquiry</h2><p>Review its submitted query, clarification answers, searches, source files and model responses.</p></div> : null}
      </section>
    </div>}
  </div>
}
