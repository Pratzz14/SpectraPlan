import { useEffect, useRef, useState } from 'react'
import { reportText } from '../assessment'
import type { AssessmentRun } from '../assessment'

export default function ActionBar({ run, description, loading, compact = false }: { run: AssessmentRun | null; description: string; loading: boolean; compact?: boolean }) {
  const [feedback, setFeedback] = useState('')
  const [manualText, setManualText] = useState<string | null>(null)
  const [copying, setCopying] = useState(false)
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
  return <section className={`action-bar${compact ? ' compact' : ''}`} aria-label="Save this run"><div className="card-heading"><div>{compact ? <span className="section-note">{loading ? 'Analyzing…' : run?.run_status === 'incomplete' ? 'Incomplete result' : run ? 'Current result' : ''}</span> : <><h2>Save this run</h2><p className="section-note">{run ? `Exports refer to run ${run.metadata.run_id}.` : 'Analyze an enquiry to create an exportable result.'}</p></>}</div><div className="action-buttons"><button className="secondary-button" type="button" disabled={!run || loading || copying} onClick={() => void copy()}>{copying ? 'Copying…' : run?.run_status === 'incomplete' ? 'Copy incomplete report' : 'Copy report'}</button><button className="primary-button" type="button" disabled={!run || loading} onClick={download}>{run?.run_status === 'incomplete' ? 'Download incomplete JSON' : 'Download JSON'}</button></div></div><p role="status" aria-live="polite" className="action-feedback">{feedback}</p>{manualText !== null && run && !loading ? <div><label htmlFor="manual-report">Report text for manual copying</label><textarea id="manual-report" readOnly value={manualText} rows={10} onFocus={event => event.currentTarget.select()} /></div> : null}</section>
}
