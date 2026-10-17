import { useEffect, useRef, useState } from 'react'
import { fetchHealth } from './api'
import type { HealthResponse } from './api'
import SearchWorkbench from './SearchWorkbench'

const corpusLabels: Record<HealthResponse['corpus']['status'], string> = {
  missing: 'Awaiting source preparation',
  unreadable: 'Corpus cannot be read',
  invalid: 'Corpus needs attention',
  empty: 'Awaiting eligible evidence',
  ready: 'Searchable evidence available',
}

export default function App() {
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
    return () => {
      activeRequest.current?.abort()
      activeRequest.current = null
    }
  }, [])

  return (
    <div className="min-h-screen bg-[#f7f8f5] text-[#1e302b]">
      <header className="border-b border-[#dce3db] px-6 py-5 sm:px-10">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4">
          <a className="text-lg font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-4" href="/">SpectraPlan<span className="text-[#48745c]">.</span></a>
          <span className="text-xs font-medium uppercase tracking-[0.15em] text-[#56685f]">Local workspace</span>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-10 sm:px-10 sm:py-12">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-[#48745c]">Process spectroscopy · Knowledge workspace</p>
        <h1 className="max-w-3xl text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">Explore sources. Compare search results.</h1>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-[#56685f]">Inspect the extracted evidence and test keyword, semantic and combined retrieval against the technical corpus and website context.</p>
        <SearchWorkbench />

        <section aria-labelledby="status-heading" aria-busy={loading} className="mt-12 rounded-2xl border border-[#dce3db] bg-white p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 id="status-heading" className="text-xl font-semibold tracking-tight">Workspace readiness</h2>
            <button onClick={() => void refresh()} disabled={loading} className="rounded-lg border border-[#c4d1c7] px-4 py-2 text-sm font-medium transition-colors hover:bg-[#edf3ee] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#48745c] disabled:cursor-wait disabled:opacity-60">{loading ? 'Checking…' : 'Refresh status'}</button>
          </div>
          <div role="status" aria-live="polite" className="mt-6">
            {loading ? <p className="text-sm text-[#56685f]">Checking the local backend…</p> : null}
            {error ? <p role="alert" className="rounded-lg bg-[#fff3ea] p-4 text-sm leading-6 text-[#804426]">{error}</p> : null}
            {health ? <>
              <p className="mb-6 text-sm font-medium text-[#48745c]">{health.ready ? 'Foundation dependencies are ready. Assessment workflow is coming in a later increment.' : 'Backend connected. Setup dependencies remain.'}</p>
              <dl className="grid gap-6 sm:grid-cols-3">
                <div><dt className="text-xs font-semibold uppercase tracking-wider text-[#68796f]">Backend</dt><dd className="mt-2 text-sm font-medium">Running</dd><dd className="mt-1 text-sm leading-6 text-[#56685f]">Local connection established</dd></div>
                <div><dt className="text-xs font-semibold uppercase tracking-wider text-[#68796f]">Knowledge base</dt><dd className="mt-2 text-sm font-medium">{corpusLabels[health.corpus.status]}</dd><dd className="mt-1 break-words text-sm leading-6 text-[#56685f]">{health.corpus.eligible_passages} searchable passages · {health.corpus.eligible_methods} method rows{health.corpus.version ? ` · ${health.corpus.version}` : ''}</dd><dd className="mt-1 text-xs leading-5 text-[#68796f]">{health.corpus.flagged_records} flagged · {health.corpus.human_verified_records} human-verified records</dd>{health.corpus.status === 'ready' ? <dd className="mt-3"><a href="/api/knowledge/report" target="_blank" rel="noreferrer" className="text-sm font-medium text-[#48745c] underline underline-offset-4">Inspect extracted knowledge</a></dd> : null}</div>
                <div><dt className="text-xs font-semibold uppercase tracking-wider text-[#68796f]">Model provider</dt><dd className="mt-2 text-sm font-medium">{health.provider.configured ? 'Configured · live verification separate' : 'API key required'}</dd><dd className="mt-1 break-all text-sm leading-6 text-[#56685f]">{health.provider.name === 'llmtech' ? 'LLMTech' : 'Groq'} · {health.provider.model}</dd></div>
              </dl>
            </> : null}
          </div>
          <p className="mt-8 border-t border-[#e6ebe5] pt-5 text-xs leading-5 text-[#68796f]">Readiness checks use the local backend and do not call the model provider.</p>
        </section>
        <p className="mt-6 max-w-2xl text-sm leading-6 text-[#68796f]">Searchable evidence passes automated source checks. Manual verification is optional. The assessment workflow follows in a later increment.</p>
      </main>
    </div>
  )
}
