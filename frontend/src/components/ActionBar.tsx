import { useEffect, useRef, useState } from 'react'
import { reportText } from '../assessment'
import type { AssessmentRun } from '../assessment'

export default function ActionBar({ run, description, loading, compact = false }: { run: AssessmentRun | null; description: string; loading: boolean; compact?: boolean }) {
  const [feedback, setFeedback] = useState('')
  const [manualText, setManualText] = useState<string | null>(null)
  const [copying, setCopying] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)
  const identity = `${loading}:${run?.metadata.run_id ?? ''}`
  const current = useRef(identity)
  current.current = identity
  useEffect(() => { setFeedback(''); setManualText(null); setCopying(false) }, [identity])
  async function copy() {
    if (!run || loading) return
    const started = current.current
    const report = reportText(run, description)
    setCopying(true); setFeedback(''); setManualText(null)
    try {
      await navigator.clipboard.writeText(report)
      if (current.current === started) setFeedback('Report copied.')
    } catch {
      if (current.current === started) { setManualText(report); setFeedback('Clipboard access is unavailable. Select and copy the report below.') }
    } finally { if (current.current === started) setCopying(false) }
  }
  function download() {
    if (!run || loading) return
    try {
      const url = URL.createObjectURL(new Blob([JSON.stringify(run, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url; link.download = `spectraplan-${run.run_status}-${run.metadata.run_id.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`
      document.body.append(link); link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setFeedback(`${run.run_status === 'incomplete' ? 'Incomplete run' : 'Run'} JSON download started.`)
    } catch { setFeedback('Download could not start. Please try again.') }
  }
  async function downloadPdf() {
    if (!run || loading || exportingPdf) return
    const started = current.current
    setExportingPdf(true); setFeedback('')
    try {
      const response = await fetch(`/api/assess/${encodeURIComponent(run.metadata.run_id)}/report.pdf`, { signal: AbortSignal.timeout(60000) })
      if (!response.ok) throw new Error(response.status === 404
        ? 'This saved analysis is no longer available. Analyze the enquiry again to create a new report.'
        : 'The PDF service could not generate the report. Please try again.')
      if (!response.headers.get('content-type')?.includes('application/pdf')) throw new Error('The PDF service returned an unexpected response. Please try again.')
      const blob = await response.blob()
      if (blob.size === 0 || await blob.slice(0, 5).text() !== '%PDF-') throw new Error('The PDF file was incomplete. Please try again.')
      if (current.current !== started) return
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = `spectraplan-${run.metadata.run_id}.pdf`
      document.body.append(link); link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
      setFeedback('PDF download started.')
    } catch (error) {
      if (current.current === started) setFeedback(error instanceof DOMException && error.name === 'TimeoutError'
        ? 'PDF generation took too long. Please try again.'
        : error instanceof TypeError ? 'Cannot reach the PDF service. Check the backend connection and try again.'
        : error instanceof Error ? error.message : 'PDF download could not start. Please try again.')
    } finally { setExportingPdf(false) }
  }
  return <section className={`action-bar${compact ? ' compact' : ''}`} aria-label="Save this run"><div className="card-heading"><div>{compact ? <span className="section-note">{loading ? 'Analyzing…' : run?.run_status === 'incomplete' ? 'Incomplete result' : run ? 'Current result' : ''}</span> : <><h2>Save this run</h2><p className="section-note">{run ? `Exports refer to run ${run.metadata.run_id}.` : 'Analyze an enquiry to create an exportable result.'}</p></>}</div><div className="action-buttons"><button className="secondary-button" type="button" disabled={!run || loading || copying} onClick={() => void copy()}>{copying ? 'Copying…' : run?.run_status === 'incomplete' ? 'Copy incomplete report' : 'Copy report'}</button><button className="secondary-button" type="button" disabled={!run || loading} onClick={download}>{run?.run_status === 'incomplete' ? 'Download incomplete JSON' : 'Download JSON'}</button><button className="primary-button" type="button" disabled={!run || loading || exportingPdf} onClick={() => void downloadPdf()}>{exportingPdf ? 'Preparing PDF…' : 'Download PDF'}</button></div></div><p role="status" aria-live="polite" className="action-feedback">{feedback}</p>{manualText !== null && run && !loading ? <div><label htmlFor="manual-report">Report text for manual copying</label><textarea id="manual-report" readOnly value={manualText} rows={10} onFocus={event => event.currentTarget.select()} /></div> : null}</section>
}
