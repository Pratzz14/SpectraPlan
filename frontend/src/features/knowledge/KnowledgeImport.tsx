import { useEffect, useRef, useState } from 'react'
import { fetchKnowledgeIngestion, uploadKnowledgeFile } from '../../shared/api/api'
import type { KnowledgeIngestion } from '../../shared/api/api'

export default function KnowledgeImport({ onComplete, expanded, onClose }: { onComplete: (sourceId?: string) => void; expanded: boolean; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [role, setRole] = useState('technical')
  const [job, setJob] = useState<KnowledgeIngestion>({ job_id: '', status: 'idle' })
  const [error, setError] = useState('')
  const [pollError, setPollError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [poll, setPoll] = useState(0)
  const completed = useRef(onComplete)
  const wasBusy = useRef(false)
  const fileInput = useRef<HTMLInputElement>(null)
  completed.current = onComplete
  const busy = job.status === 'queued' || job.status === 'running'

  useEffect(() => {
    if (!expanded) {
      setFile(null)
      if (fileInput.current) fileInput.current.value = ''
    }
  }, [expanded])

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    async function update() {
      try {
        const status = await fetchKnowledgeIngestion(controller.signal)
        if (controller.signal.aborted) return
        setJob(status)
        setPollError('')
        const running = status.status === 'queued' || status.status === 'running'
        if (wasBusy.current && status.status === 'succeeded') {
          completed.current(status.source_id)
          setFile(null)
          if (fileInput.current) fileInput.current.value = ''
        }
        wasBusy.current = running
        if (running) timer = setTimeout(() => { void update() }, 2000)
      } catch (reason) {
        if (!controller.signal.aborted) {
          setPollError(reason instanceof Error ? reason.message : 'Could not load ingestion progress.')
          timer = setTimeout(() => { void update() }, 4000)
        }
      }
    }
    void update()
    return () => { controller.abort(); if (timer) clearTimeout(timer) }
  }, [poll])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!file) return
    setError('')
    if (!/\.(pdf|xlsx|docx)$/i.test(file.name)) { setError('Choose a PDF, Excel (.xlsx), or Word (.docx) file.'); return }
    if (!file.size || file.size > (job.max_bytes ?? 52428800)) { setError('Choose a nonempty file within the upload size limit.'); return }
    setSubmitting(true)
    try {
      const state = await uploadKnowledgeFile(file, role)
      wasBusy.current = true
      setJob(value => ({ ...value, ...state }))
      onClose()
      setPoll(value => value + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'File upload failed.')
    } finally { setSubmitting(false) }
  }

  const count = job.progress?.completed ?? 0
  const total = job.progress?.total ?? 0
  if (!expanded && !submitting && !busy && job.status !== 'failed' && !pollError && !error) return null
  return <section id="knowledge-import" className="knowledge-import" aria-label="Add knowledge files">
    <div className="import-toolbar">
      <div aria-live="polite">{submitting ? <span>Uploading file…</span> : busy ? <><strong>{job.filename ?? 'Knowledge ingestion'}</strong><span> · {job.message ?? 'Extracting knowledge'}{total ? ` · ${count}/${total} locations completed` : ''}</span></> : job.status === 'succeeded' ? <span>{job.filename ?? 'File'} · added to extracted knowledge</span> : null}</div>
    </div>
    {busy && total ? <progress aria-label="Extraction progress" max={total} value={count} /> : null}
    {job.progress?.fallback || job.progress?.unreadable ? <p className="section-note">{job.progress.fallback ?? 0} locations recovered locally · {job.progress.unreadable ?? 0} unreadable. Inspect source pages for extraction details.</p> : null}
    {job.status === 'failed' ? <p role="alert">{job.message ?? 'Extraction failed. Existing knowledge was preserved.'}</p> : null}
    {pollError ? <p role="status">{pollError}</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {expanded ? <form className="knowledge-upload-form" onSubmit={e => { void submit(e) }}>
      <label>New file<input ref={fileInput} type="file" accept=".pdf,.xlsx,.docx" disabled={busy || submitting} onChange={e => { setFile(e.target.files?.[0] ?? null); setError('') }} /></label>
      <label>Source type<select aria-label="New file source type" value={role} disabled={busy || submitting} onChange={e => setRole(e.target.value)}><option value="technical">Technical reference</option><option value="research">Research study</option><option value="business">Business context</option><option value="development">Examples and worked answers</option></select></label>
      <p className="section-note">PDF, Excel and Word · up to {Math.floor((job.max_bytes ?? 52428800) / 1048576)} MB. Files with the same name update that source. Your existing library is retained.</p>
      {job.qwen_configured === false ? <p className="section-note">Qwen is not configured. This file will use local embedded-text extraction or OCR.</p> : <p className="section-note">Sends the selected file's contents to {job.endpoint_host?.endsWith('aliyuncs.com') ? 'Alibaba DashScope' : job.endpoint_host ?? 'the configured model service'} for Qwen3.8 Flash extraction, with bounded retries and local text/OCR fallback.</p>}
      <button type="submit" className="primary-button" disabled={!file || busy || submitting}>{submitting ? 'Uploading…' : busy ? 'Another ingestion is running' : job.qwen_configured === false ? 'Add and extract locally' : 'Add and extract with Qwen'}</button>
    </form> : null}
  </section>
}
