import { useEffect, useRef, useState } from 'react'
import { fetchHealth } from '../../shared/api/api'
import type { HealthResponse } from '../../shared/api/api'

const corpusLabels: Record<HealthResponse['corpus']['status'], string> = {
  missing: 'Awaiting source preparation',
  unreadable: 'Corpus cannot be read',
  invalid: 'Corpus needs attention',
  empty: 'Awaiting eligible evidence',
  ready: 'Searchable evidence available',
}

export default function WorkspaceStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const activeRequest = useRef<AbortController | null>(null)

  async function refresh() {
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    setLoading(true)
    setError(null)
    setHealth(null)
    const timeout = window.setTimeout(() => controller.abort('timeout'), 8000)
    try {
      const result = await fetchHealth(controller.signal)
      if (activeRequest.current === controller && !controller.signal.aborted) setHealth(result)
    } catch {
      if (activeRequest.current === controller) {
        setError('Cannot reach the backend. Check that the local service is running, then refresh.')
      }
    } finally {
      window.clearTimeout(timeout)
      if (activeRequest.current === controller) setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    return () => { activeRequest.current?.abort(); activeRequest.current = null }
  }, [])

  return (
        <section aria-labelledby="status-heading" aria-busy={loading} className="rounded-2xl border border-[#dce3db] bg-white p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 id="status-heading" className="text-xl font-semibold tracking-tight">Workspace readiness</h2>
            <button onClick={() => void refresh()} disabled={loading} className="rounded-lg border border-[#c4d1c7] px-4 py-2 text-sm font-medium transition-colors hover:bg-[#edf3ee] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#48745c] disabled:cursor-wait disabled:opacity-60">{loading ? 'Checking…' : 'Refresh status'}</button>
          </div>
          <div role="status" aria-live="polite" className="mt-6">
            {loading ? <p className="text-sm text-[#56685f]">Checking the local backend…</p> : null}
            {error ? <p role="alert" className="rounded-lg bg-[#fff3ea] p-4 text-sm leading-6 text-[#804426]">{error}</p> : null}
            {health ? <>
              <p className="mb-6 text-sm font-medium text-[#48745c]">{health.ready ? 'Dependencies are ready for assessment.' : 'Backend connected. Check the dependencies below before analyzing an enquiry.'}</p>
              <dl className="grid gap-6 sm:grid-cols-3">
                <div><dt className="text-xs font-semibold uppercase tracking-wider text-[#68796f]">Backend</dt><dd className="mt-2 text-sm font-medium">Running</dd><dd className="mt-1 text-sm leading-6 text-[#56685f]">Local connection established</dd></div>
                <div><dt className="text-xs font-semibold uppercase tracking-wider text-[#68796f]">Knowledge base</dt><dd className="mt-2 text-sm font-medium">{corpusLabels[health.corpus.status]}</dd><dd className="mt-1 break-words text-sm leading-6 text-[#56685f]">{health.corpus.eligible_passages} searchable passages · {health.corpus.eligible_methods} method rows{health.corpus.version ? ` · ${health.corpus.version}` : ''}</dd><dd className="mt-1 text-xs leading-5 text-[#68796f]">{health.corpus.flagged_records} flagged · {health.corpus.human_verified_records} human-verified records</dd>{health.corpus.status === 'ready' ? <dd className="mt-3"><a href="#knowledge" className="text-sm font-medium text-[#48745c] underline underline-offset-4">Inspect extracted knowledge</a></dd> : null}</div>
                <div><dt className="text-xs font-semibold uppercase tracking-wider text-[#68796f]">Model provider</dt><dd className="mt-2 text-sm font-medium">{health.provider.configured ? 'Alibaba Cloud · configured' : 'DashScope API key required'}</dd><dd className="mt-1 break-all text-sm leading-6 text-[#56685f]">Qwen · {health.provider.model}</dd></div>
              </dl>
            </> : null}
          </div>
          <p className="mt-8 border-t border-[#e6ebe5] pt-5 text-xs leading-5 text-[#68796f]">Status refresh reads cached availability. Automatic selection checks providers at startup and when needed, using a small synthetic request.</p>
        </section>
  )
}
