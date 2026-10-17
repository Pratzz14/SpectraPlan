import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchSearchStatus, queryKnowledge } from './api'
import type { SearchDataset, SearchHit, SearchMode, SearchResponse, SearchStatus } from './api'

const modes = [
  {value: 'compare', label: 'Compare all'}, {value: 'bm25', label: 'BM25 keywords'},
  {value: 'qdrant', label: 'Qdrant semantic'}, {value: 'hybrid', label: 'Hybrid'},
] as const
const engines = {
  bm25: {title: 'BM25', description: 'Keyword relevance', score: 'BM25 score'},
  qdrant: {title: 'Qdrant', description: 'Semantic similarity · local BGE embeddings', score: 'Cosine similarity'},
  hybrid: {title: 'Hybrid', description: 'Combined ranks · reciprocal rank fusion', score: 'RRF score'},
}
const field = 'mt-2 w-full rounded-lg border border-[#c4d1c7] bg-white px-3 py-2.5 text-sm text-[#1e302b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#48745c]'

function safeUrl(value?: string) {
  if (!value) return undefined
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : undefined } catch { return undefined }
}

function ResultCard({hit, engine, version}: {hit: SearchHit; engine: keyof typeof engines; version?: string}) {
  const evidence = hit.evidence
  const website = evidence.dataset === 'website'
  const source = website ? safeUrl(evidence.location_url || evidence.url) : undefined
  const report = !website && version ? `/api/knowledge/versions/${encodeURIComponent(version)}/review.html` : undefined
  return <article className="min-w-0 rounded-xl border border-[#dce3db] bg-white p-5">
    <div className="flex items-start justify-between gap-3"><span className="text-xs font-semibold text-[#68796f]">#{hit.rank}</span><span className="text-right text-xs text-[#56685f]">{engines[engine].score}<strong className="ml-2 font-mono text-[#1e302b]">{hit.score.toFixed(engine === 'hybrid' ? 5 : 4)}</strong></span></div>
    <h4 className="mt-3 text-base font-semibold leading-6">{evidence.section}</h4>
    <p className="mt-2 break-words text-xs leading-5 text-[#56685f]">{website ? evidence.page_title : `${evidence.source_id} · ${evidence.content_kind === 'method_row' ? `${evidence.sheet} row ${evidence.row} · underlying S01 PDF page 6` : `PDF page ${evidence.page}`}`}</p>
    <div className="mt-3 flex flex-wrap gap-2 text-xs"><span className={`rounded-full px-2.5 py-1 ${website ? 'bg-[#fff2df] text-[#83541d]' : 'bg-[#edf3ee] text-[#386346]'}`}>{website ? 'Website · business context' : 'Technical corpus'}</span><span className="rounded-full bg-[#f1f3f0] px-2.5 py-1 text-[#56685f]">{evidence.evidence_scope.replaceAll('_', ' ')}</span></div>
    <p className="mt-4 whitespace-pre-wrap break-words text-sm leading-6 text-[#344b40]">{evidence.text.length > 550 ? evidence.text.slice(0, 550) + '…' : evidence.text}</p>
    {hit.matched_terms.length > 0 ? <p className="mt-4 break-words text-xs leading-5 text-[#56685f]"><span className="font-semibold">Matched words: </span>{hit.matched_terms.join(', ')}</p> : null}
    <p className="mt-3 text-xs text-[#68796f]">Found by {hit.branches.join(' + ')}</p>
    {website && evidence.fetched_at ? <p className="mt-2 text-xs text-[#68796f]">Crawled {new Date(evidence.fetched_at).toLocaleString()}</p> : null}
    {(source || report) ? <a href={source || report} target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm font-medium text-[#386346] underline underline-offset-4">{website ? 'Open website source' : 'Open corpus inspection report'}</a> : null}
    <details className="mt-4 border-t border-[#e6ebe5] pt-3"><summary className="cursor-pointer text-xs font-semibold text-[#56685f]">Full text and provenance</summary>
      <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6">{evidence.text}</p>
      {hit.matching_segment ? <div className="mt-4 border-l-2 border-[#7fa58a] pl-3"><p className="text-xs font-semibold text-[#56685f]">Best semantic segment</p><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{hit.matching_segment}</p></div> : null}
      <dl className="mt-4 space-y-2 break-all text-xs leading-5 text-[#68796f]"><div><dt className="font-semibold">Evidence ID</dt><dd>{evidence.evidence_id}</dd></div><div><dt className="font-semibold">Revision</dt><dd>{evidence.revision}</dd></div><div><dt className="font-semibold">Source SHA-256</dt><dd>{evidence.source_sha256}</dd></div>{website ? <><div><dt className="font-semibold">Snapshot location</dt><dd>{evidence.selector}</dd></div><div><dt className="font-semibold">Source check</dt><dd>{evidence.validation_basis}</dd></div></> : null}</dl>
    </details>
  </article>
}

export default function SearchWorkbench() {
  const [status, setStatus] = useState<SearchStatus | null>(null)
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<SearchMode>('compare')
  const [dataset, setDataset] = useState<SearchDataset>('technical')
  const [limit, setLimit] = useState(6)
  const [expand, setExpand] = useState(true)
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const active = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void fetchSearchStatus(controller.signal).then(setStatus).catch(() => { if (!controller.signal.aborted) setError('Cannot load search datasets. Check the backend, then try a search.') })
    return () => { controller.abort(); active.current?.abort() }
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    setLoading(true); setError(null); setResult(null)
    const timeout = window.setTimeout(() => controller.abort('timeout'), 120000)
    try {
      const response = await queryKnowledge({query: query.trim(), mode, dataset, limit, expand_synonyms: expand}, controller.signal)
      if (active.current === controller && !controller.signal.aborted) setResult(response)
    } catch (caught) {
      if (active.current === controller) setError(controller.signal.aborted ? 'Search timed out. Try again or choose BM25 keyword search.' : caught instanceof Error ? caught.message : 'Search is unavailable.')
    } finally {
      window.clearTimeout(timeout)
      if (active.current === controller) setLoading(false)
    }
  }

  function download() {
    if (!result) return
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'}))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'spectraplan-search.json'; anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return <section id="search" aria-labelledby="search-heading" className="mt-12 scroll-mt-6">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#48745c]">Explore the evidence</p><h2 id="search-heading" className="mt-3 text-3xl font-semibold tracking-tight">Search the knowledge base</h2></div><span className="text-xs text-[#68796f]">Local search · no Qwen calls</span></div>
    <p className="mt-4 max-w-3xl text-sm leading-6 text-[#56685f]">Try exact keywords, a natural-language question, or compare all three rankings. Scores describe relevance within each search method; they are not confidence percentages.</p>
    <div className="mt-6 grid gap-3 sm:grid-cols-2" aria-label="Search datasets">
      <div className="rounded-xl border border-[#dce3db] bg-white p-4"><p className="text-sm font-semibold">Technical corpus</p><p className="mt-1 text-xs leading-5 text-[#56685f]">{status?.technical.status === 'ready' ? `${status.technical.records} searchable passages and method rows` : 'Check corpus readiness before searching'}</p></div>
      <div className="rounded-xl border border-[#e3d9c6] bg-[#fffcf5] p-4"><p className="text-sm font-semibold">Crawled website context</p><p className="mt-1 text-xs leading-5 text-[#56685f]">{status?.website.status === 'ready' ? `${status.website.pages} pages · ${status.website.records} text records · ${new Date(status.website.fetched_at!).toLocaleDateString()}` : 'No website snapshot available'}</p>{status?.website.seed_url ? <a className="mt-1 block break-all text-xs text-[#386346] underline" href={safeUrl(status.website.seed_url)} target="_blank" rel="noreferrer">{status.website.seed_url}</a> : null}</div>
    </div>
    <form onSubmit={event => void submit(event)} className="mt-6 rounded-2xl border border-[#dce3db] bg-white p-5 sm:p-7">
      <label htmlFor="knowledge-query" className="text-sm font-semibold">Search query</label>
      <textarea id="knowledge-query" value={query} onChange={event => setQuery(event.target.value)} maxLength={2000} rows={3} className={field + ' resize-y'} placeholder="For example: powder blend API concentration, opaque dairy fat protein, or 785 nm Raman probe" />
      <div className="mt-4 grid gap-4 sm:grid-cols-3"><label className="text-xs font-semibold text-[#56685f]">Search method<select aria-label="Search method" value={mode} onChange={event => setMode(event.target.value as SearchMode)} className={field}>{modes.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <label className="text-xs font-semibold text-[#56685f]">Dataset<select aria-label="Dataset" value={dataset} onChange={event => setDataset(event.target.value as SearchDataset)} className={field}><option value="technical">Technical corpus</option><option value="website">Website context</option><option value="all">Technical + website context</option></select></label>
        <label className="text-xs font-semibold text-[#56685f]">Results per method<select aria-label="Results per method" value={limit} onChange={event => setLimit(Number(event.target.value))} className={field}>{[4, 6, 8].map(n => <option key={n} value={n}>{n} results</option>)}</select></label></div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4"><label className="flex items-center gap-2 text-xs leading-5 text-[#56685f]"><input type="checkbox" checked={expand} onChange={event => setExpand(event.target.checked)} className="h-4 w-4 accent-[#386346]" />Expand keyword synonyms (for example, moisture → water)</label><button type="submit" disabled={!query.trim() || loading} className="rounded-lg bg-[#315e43] px-6 py-3 text-sm font-semibold text-white hover:bg-[#234b34] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#48745c] disabled:cursor-not-allowed disabled:opacity-50">{loading ? 'Searching…' : 'Run search'}</button></div>
      <p className="mt-4 text-xs leading-5 text-[#68796f]">BM25 can run without embeddings. Semantic search loads the local embedding model on its first request. Website statements retain their business-context scope.</p>
    </form>
    {loading ? <p role="status" className="mt-6 text-sm text-[#56685f]">Searching the selected local indexes…</p> : null}
    {error ? <p role="alert" className="mt-6 rounded-lg border border-[#efd8bd] bg-[#fff3ea] p-4 text-sm leading-6 text-[#804426]">{error}</p> : null}
    {result ? <div className="mt-8" aria-live="polite"><div className="flex flex-wrap items-start justify-between gap-4"><div><h3 className="text-lg font-semibold">Results for “{result.query}”</h3><p className="mt-1 text-xs leading-5 text-[#68796f]">{result.elapsed_ms.toFixed(0)} ms · {result.dataset === 'all' ? 'Technical + website context' : result.dataset === 'technical' ? 'Technical corpus' : 'Website context'} · {result.model_calls} Qwen calls</p></div><button onClick={download} className="rounded-lg border border-[#c4d1c7] bg-white px-4 py-2 text-xs font-semibold hover:bg-[#edf3ee]">Download search JSON</button></div>
      {result.expanded_terms.length ? <p className="mt-3 text-xs leading-5 text-[#56685f]">Added keyword terms: {result.expanded_terms.join(', ')}</p> : null}
      {result.warnings.map(warning => <p key={warning} className="mt-3 rounded-lg border border-[#e3d9c6] bg-[#fffcf5] p-3 text-xs leading-5 text-[#83541d]">{warning}</p>)}
      <div className={`mt-6 grid items-start gap-5 ${result.mode === 'compare' ? 'xl:grid-cols-3' : ''}`}>{(Object.keys(result.rankings) as (keyof typeof engines)[]).map(engine => <section key={engine} aria-label={`${engines[engine].title} results`} className="min-w-0"><div className="mb-4 border-b border-[#cdd9cf] pb-3"><h3 className="text-lg font-semibold">{engines[engine].title} <span className="ml-2 text-xs font-normal text-[#68796f]">{result.rankings[engine]!.length} results</span></h3><p className="mt-1 text-xs leading-5 text-[#68796f]">{engines[engine].description}</p></div><div className="space-y-4">{result.rankings[engine]!.length ? result.rankings[engine]!.map(hit => <ResultCard key={hit.evidence.evidence_id} hit={hit} engine={engine} version={result.versions.technical} />) : <p className="rounded-xl border border-dashed border-[#c4d1c7] p-5 text-sm text-[#68796f]">No matches for this method. Try a different query.</p>}</div></section>)}</div>
      <details className="mt-6 text-xs text-[#68796f]"><summary className="cursor-pointer font-semibold">Dataset versions</summary><pre className="mt-2 whitespace-pre-wrap break-all">{JSON.stringify(result.versions, null, 2)}</pre></details>
    </div> : null}
  </section>
}
