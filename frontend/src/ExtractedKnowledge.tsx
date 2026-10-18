import ExternalLinkIcon from './components/ExternalLinkIcon'
import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchGeminiComparison, fetchKnowledgeInspection } from './api'
import type { GeminiComparison } from './api'
import { readable } from './assessment'
import { recordTitle, sourcePageFor, sourcePageUrl } from './knowledge'
import type { KnowledgeInspection, KnowledgeRecord, SourcePage } from './knowledge'

function PagePreview({ data, page, record, highlight }: { data: KnowledgeInspection; page: SourcePage; record: KnowledgeRecord; highlight: boolean }) {
  const src = sourcePageUrl(data, page)
  const regions = record.region ? [record.region] : (record.source_spans ?? []).filter(s => s.bbox?.length === 4).map(s => ({ x0: s.bbox[0] / page.width, y0: s.bbox[1] / page.height, x1: s.bbox[2] / page.width, y1: s.bbox[3] / page.height }))
  return <><figure className="source-preview">{src ? <><img src={src} alt={`${page.source_id} original source page ${page.page}`} loading="lazy" />{highlight ? regions.map((r, i) => <span key={i} className="source-region" style={{ left: `${r.x0 * 100}%`, top: `${r.y0 * 100}%`, width: `${(r.x1 - r.x0) * 100}%`, height: `${(r.y1 - r.y0) * 100}%` }} />) : null}</> : <p className="section-note">Source image is unavailable.</p>}</figure><details><summary>Raw extracted text</summary><pre className="source-text">{page.blocks.map(b => b.text).join('\n\n')}</pre></details></>
}

export default function ExtractedKnowledge({ initialEvidence = '' }: { initialEvidence?: string }) {
  const [data, setData] = useState<KnowledgeInspection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [kind, setKind] = useState('')
  const [status, setStatus] = useState('')
  const [pageNumber, setPageNumber] = useState('')
  const [eligible, setEligible] = useState('')
  const [selected, setSelected] = useState(initialEvidence)
  const [tab, setTab] = useState<'text' | 'page' | 'provenance'>('text')
  const [pageChoice, setPageChoice] = useState('auto')
  const [attempt, setAttempt] = useState(0)
  const [gemini, setGemini] = useState<GeminiComparison | null>(null)
  const [geminiError, setGeminiError] = useState<string | null>(null)
  const recordButtons = useRef(new Map<string, HTMLButtonElement>())
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(null)
    void fetchKnowledgeInspection(controller.signal).then(value => {
      if (!controller.signal.aborted) setData(value)
    })
      .catch(failure => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Cannot load extracted knowledge.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    setGeminiError(null)
    void fetchGeminiComparison(controller.signal).then(value => { if (!controller.signal.aborted) setGemini(value) })
      .catch(failure => { if (!controller.signal.aborted) { setGemini(null); setGeminiError(failure instanceof Error ? failure.message : 'Comparison unavailable.') } })
    return () => controller.abort()
  }, [attempt])
  useEffect(() => { if (initialEvidence) { setSelected(initialEvidence); setQuery(''); setSource(''); setKind(''); setStatus(''); setEligible(''); setPageNumber(''); setPageChoice('auto') } }, [initialEvidence])
  const indexed = useMemo(() => data?.records.map(record => ({ record, search: JSON.stringify(record).toLowerCase() })) ?? [], [data])
  const records = useMemo(() => indexed.filter(({ record: r, search }) => (!query || search.includes(query.toLowerCase())) && (!source || r.source_id === source) && (!kind || r.content_kind === kind) && (!status || r.validation_status === status) && (!pageNumber || r.page === Number(pageNumber)) && (!eligible || String(r.retrieval_eligible) === eligible)).map(item => item.record), [indexed, query, source, kind, status, pageNumber, eligible])
  const record = records.find(r => r.evidence_id === selected) ?? records[0]
  const autoPage = data && record ? sourcePageFor(data, record) : undefined
  const page = pageChoice === 'auto' ? autoPage : data?.pages[Number(pageChoice)]
  const imageUrl = data && autoPage ? sourcePageUrl(data, autoPage) : undefined
  function selectRecord(id: string) { setSelected(id); setPageChoice('auto') }
  return <div className="knowledge-page"><div className="gemini-panel">{gemini ? <><div><h2>Gemini extraction comparison</h2><p>{gemini.succeeded}/{gemini.source_count} sources succeeded with {gemini.model}.</p></div><details><summary>View Gemini results</summary><div className="gemini-results">{gemini.results.map(result => <article key={result.source_id}><h3>{result.source_id} · {result.file_name}</h3>{result.gemini ? <><h4>Facts</h4><ul>{result.gemini.facts.map((fact, i) => <li key={i}>{fact}</li>)}</ul><h4>Claims</h4><ul>{result.gemini.claims.map((claim, i) => <li key={i}>{claim}</li>)}</ul><h4>Unknowns</h4><ul>{result.gemini.unknowns.map((unknown, i) => <li key={i}>{unknown}</li>)}</ul><small>Locations: {result.gemini.source_locations.join(', ')}</small></> : <p className="flagged">Error: {result.error?.code}</p>}</article>)}</div></details></> : <p>{geminiError ?? 'Gemini comparison not available. Run the comparison command and refresh this page.'} <button type="button" className="text-button" onClick={() => setAttempt(a => a + 1)}>Retry comparison</button></p>}</div><div className="split-workspace knowledge-workspace">
    <aside className="workspace-rail records-rail" aria-label="Knowledge filters">
      <div className="rail-controls"><h1>Records</h1><label className="visually-hidden" htmlFor="record-query">Search extracted text</label><input id="record-query" type="search" placeholder="Search extracted text" value={query} onChange={e => setQuery(e.target.value)} />
        <div className="filter-pair"><label>Source<select aria-label="Source" value={source} onChange={e => setSource(e.target.value)}><option value="">All sources</option>{[...new Set(data?.records.map(r => r.source_id) ?? [])].map(id => <option key={id}>{id}</option>)}</select></label><label>Content<select aria-label="Content" value={kind} onChange={e => setKind(e.target.value)}><option value="">All content</option><option value="verbatim_text">Text</option><option value="figure_transcription">Figure transcription</option><option value="method_row">Workbook</option></select></label></div>
        <label>Status<select aria-label="Status" value={status} onChange={e => setStatus(e.target.value)}><option value="">All records</option><option value="passed">Passed automated checks</option><option value="flagged">Flagged</option></select></label>
        <details className="advanced-filters"><summary>More filters</summary><label>Page<input type="number" min="1" value={pageNumber} onChange={e => setPageNumber(e.target.value)} placeholder="All pages" /></label><label>Retrieval<select aria-label="Retrieval" value={eligible} onChange={e => setEligible(e.target.value)}><option value="">All records</option><option value="true">Eligible</option><option value="false">Excluded</option></select></label></details>
      </div>
      <div className="records-list" aria-label="Evidence records">{loading ? <p role="status" className="section-note">Loading records…</p> : records.length ? records.map((r, index) => <button type="button" key={r.evidence_id} ref={el => { if (el) recordButtons.current.set(r.evidence_id, el); else recordButtons.current.delete(r.evidence_id) }} aria-pressed={record?.evidence_id === r.evidence_id} onClick={() => selectRecord(r.evidence_id)} onKeyDown={event => {
        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
        event.preventDefault()
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? records.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + records.length) % records.length
        recordButtons.current.get(records[next].evidence_id)?.focus(); selectRecord(records[next].evidence_id)
      }}><span className="record-icon" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6" /></svg></span><span><strong>{recordTitle(r)}</strong><small>{r.source_id}{r.content_kind === 'method_row' ? ` · ${r.sheet} row ${r.row}` : r.page ? ` · p.${r.page}` : ''} · {r.content_kind === 'method_row' ? 'Workbook' : r.content_kind === 'figure_transcription' ? 'Figure' : 'Text'}</small>{r.validation_status === 'flagged' ? <small className="flagged">Flagged · {r.retrieval_eligible ? 'Eligible' : 'Excluded'}</small> : null}</span></button>) : <p className="section-note" role="status">No matching records.</p>}</div>
      <details className="corpus-details"><summary>Corpus details</summary>{data ? <><p>{data.manifest.corpus_version}</p><p>{data.records.length} records · {data.records.filter(r => r.retrieval_eligible).length} eligible</p>{data.manifest.sources.map(s => <p key={s.source_id}>{s.source_id} · {s.file_name} · {s.role}</p>)}<details><summary>Page coverage</summary><pre>{JSON.stringify(data.manifest.coverage, null, 2)}</pre></details></> : null}</details>
    </aside>
    <section className="workspace-results knowledge-inspector" aria-label="Source inspector">
      {error ? <div className="error-panel" role="alert"><p>{error}</p><button className="secondary-button" onClick={() => setAttempt(value => value + 1)}>Retry</button></div> : null}
      {data && record ? <><div className="inspector-heading"><div><h2>{recordTitle(record)}</h2><p>{record.file_name}{record.page ? ` · page ${record.page}` : ''}</p></div>{imageUrl ? <a href={imageUrl} target="_blank" rel="noreferrer">Open source page <ExternalLinkIcon /></a> : null}</div>
        <div className="inspector-tabs" role="tablist" aria-label="Record view">{(['text', 'page', 'provenance'] as const).map((value, index, values) => <button key={value} id={`tab-${value}`} type="button" role="tab" tabIndex={tab === value ? 0 : -1} aria-selected={tab === value} aria-controls="record-tabpanel" onClick={() => setTab(value)} onKeyDown={event => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
          event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index + (event.key === 'ArrowRight' ? 1 : -1) + 3) % 3
          setTab(values[next]); document.getElementById(`tab-${values[next]}`)?.focus()
        }}>{value === 'text' ? 'Extracted text' : value === 'page' ? 'Source page' : 'Provenance'}</button>)}</div>
        <div id="record-tabpanel" className="inspector-content" role="tabpanel" aria-labelledby={`tab-${tab}`}>
          {tab === 'text' ? <><h3>{record.content_kind === 'figure_transcription' ? 'Figure transcription' : record.content_kind === 'method_row' ? 'Workbook-derived method row' : 'Source excerpt'}</h3><p className="source-excerpt">{record.text}</p><dl className="inspection-fields"><div><dt>Evidence scope</dt><dd>{readable(record.evidence_scope)}</dd></div><div><dt>Content type</dt><dd>{readable(record.content_kind)}</dd></div><div><dt>Automated checks</dt><dd>{readable(record.validation_status)}</dd></div><div><dt>Human review</dt><dd>{readable(record.human_review_status)}</dd></div><div><dt>Retrieval</dt><dd>{record.retrieval_eligible ? 'Eligible' : 'Excluded'}</dd></div></dl><p className="section-note">Source scope does not establish suitability for a new application.</p>
            <details className="inspector-disclosure"><summary>Structured facts</summary>{record.facts?.map((fact, i) => <div key={i}><p>{fact.category}: {fact.statement}</p>{fact.quantities?.map((q, j) => <p key={j}>{q.label}: {q.value} {q.unit}<br /><small>{q.source_quote}</small></p>)}</div>)}{record.raw_values ? <dl className="fact-list">{Object.entries(record.raw_values).map(([key, value]) => <div key={key}><dt>{readable(key)}</dt><dd>{String(value)}</dd></div>)}</dl> : null}</details>
            {record.content_kind === 'method_row' ? <details className="inspector-disclosure"><summary>Workbook provenance and notes</summary><p>Underlying source: {record.underlying_citation?.source_id ?? 'S01'} · {record.underlying_citation?.table ?? 'Table 1'} · p.{record.underlying_citation?.page ?? 6}</p><ul className="result-list">{data.notes.map((note, i) => <li key={i}>{note.text} <small>({note.sheet} row {note.row})</small></li>)}</ul></details> : null}
            <details className="inspector-disclosure"><summary>Recorded issues</summary>{record.issues.length ? <ul className="result-list">{record.issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul> : <p>No recorded issues.</p>}</details></> : null}
          {tab === 'page' ? <><label>Source page<select aria-label="Source page" value={pageChoice} onChange={e => setPageChoice(e.target.value)}><option value="auto">Cited page</option>{data.pages.map((p, i) => <option key={`${p.source_id}:${p.page}`} value={i}>{p.source_id} · page {p.page}</option>)}</select></label>{page ? <PagePreview data={data} page={page} record={record} highlight={pageChoice === 'auto'} /> : <p>No source image is available for this record. Select another page above.</p>}</> : null}
          {tab === 'provenance' ? <dl className="fact-list">{Object.entries({ 'Evidence ID': record.evidence_id, 'Corpus version': data.manifest.corpus_version, Revision: record.revision, 'Source SHA-256': record.source_sha256, 'Source filename': record.file_name }).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl> : null}
        </div></> : !error ? <p className="empty-workspace" role="status">{loading ? 'Loading extracted knowledge…' : 'Select a matching source record.'}</p> : null}
    </section>
  </div></div>
}
