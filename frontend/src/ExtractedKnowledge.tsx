import { useEffect, useMemo, useState } from 'react'
import { fetchKnowledgeInspection, queryKnowledge } from './api'
import type { KnowledgeInspection, KnowledgeRecord, SourcePage } from './knowledge'
import { recordTitle, sourcePageFor, sourcePageUrl, sourceUnitKey } from './knowledge'
import { readable } from './assessment'
import KnowledgeImport from './components/KnowledgeImport'

const extractionLabel = (method?: string) => ({ qwen: 'Qwen3.7 Flash', pymupdf_embedded: 'Embedded PDF text · PyMuPDF', pymupdf_ocr: 'Local OCR · PyMuPDF/Tesseract', office_text: 'Original Office text', unreadable: 'No readable text recovered' }[method ?? 'qwen'] ?? method)

function SourcePreview({ data, page }: { data: KnowledgeInspection; page: SourcePage }) {
  const [zoom, setZoom] = useState(100)
  const [failed, setFailed] = useState(false)
  const image = sourcePageUrl(data, page)
  useEffect(() => { setFailed(false); setZoom(100) }, [image])
  const pdf = `${data.artifact_base}source/${encodeURIComponent(page.source_id)}/original${!page.format || page.format === 'pdf' ? `#page=${page.page}` : ''}`
  const isPdf = !page.format || page.format === 'pdf'
  return <>
    <div className="source-toolbar"><span>{page.source_id} · {page.label ?? `page ${page.page}`}</span><a href={pdf} target="_blank" rel="noreferrer">{isPdf ? 'Open original PDF ↗' : 'Download original file ↗'}</a></div>
    {isPdf ? <><label className="zoom-control">Zoom <input aria-label="Source zoom" type="range" min="75" max="200" step="25" value={zoom} onChange={e => setZoom(Number(e.target.value))} /><span>{zoom}%</span></label>
    <div className="pdf-page-scroll">{image && !failed ? <img className="pdf-page-image" src={image} alt={`${page.source_id} original PDF page ${page.page}`} style={{ width: `${zoom}%` }} onError={() => setFailed(true)} /> : <p role="status">Source page image is unavailable. Try the original PDF link.</p>}</div>
    </> : <div className="office-source-preview">
      <p className="section-note">Source {page.format === 'workbook' ? 'cells and formulas' : 'paragraphs and table rows'}. This text preview preserves content and locations; download the original for its full formatting.</p>
      {page.rows ? <div className="source-table-scroll"><table className="source-cells"><tbody>{page.rows.map(row => <tr key={row.row}><th scope="row">{row.row}</th>{row.cells.map(cell => <td key={cell.cell}><small>{cell.cell}</small><span>{String(cell.value ?? '')}</span></td>)}</tr>)}</tbody></table></div>
        : page.blocks.map((block, i) => <div className="source-paragraph" key={i}><small>{block.location}</small><p>{block.text}</p></div>)}
    </div>}
    {page.extraction_method === 'unreadable' ? <p role="status" className="extraction-notice">No readable text was recovered. The original source remains available for inspection.</p> : null}
    {page.extraction_warnings?.length ? <ul className="section-note">{page.extraction_warnings.map((warning,i) => <li key={i}>{warning}</li>)}</ul> : null}
    {page.page_title ? <p className="section-note">{page.page_title}</p> : null}
    {page.page_limitations?.length ? <div><h3>Page limitations</h3><ul>{page.page_limitations.map((v, i) => <li key={i}>{v}</li>)}</ul></div> : null}
    {page.unreadable_regions?.length ? <div><h3>Unreadable regions</h3><ul>{page.unreadable_regions.map((v, i) => <li key={i}>{v}</li>)}</ul></div> : null}
  </>
}

function RecordDetail({ record }: { record: KnowledgeRecord }) {
  const knowledge = record.knowledge
  return <>
    <h2>{recordTitle(record)}</h2>
    <p className="section-note">{record.file_name} · {record.source_location ?? (record.page ? `page ${record.page}` : 'source record')}</p>
    <h3>{knowledge ? 'Extracted supporting text' : record.content_kind === 'method_row' ? 'Original workbook values' : 'Extracted source text'}</h3>
    <blockquote className="source-excerpt">{record.text}</blockquote>
    {knowledge ? <>
      <p className="section-note">Transcribed by {record.extraction_model}. Readability checks passed; human review: {readable(record.human_review_status)}.</p>
      <dl className="fact-list"><div><dt>Category</dt><dd>{readable(knowledge.category)}</dd></div><div><dt>Evidence kind</dt><dd>{readable(knowledge.evidence_kind)}</dd></div><div><dt>Claim scope</dt><dd>{readable(knowledge.scope)}</dd></div></dl>
      <h3>Relevance</h3><p>{knowledge.relevance}</p>
      {knowledge.quantities.length ? <><h3>Quantities</h3><ul>{knowledge.quantities.map((q, i) => <li key={i}><strong>{q.value} {q.unit}</strong> — {q.meaning}</li>)}</ul></> : null}
      {knowledge.caveat ? <><h3>Caveat</h3><p>{knowledge.caveat}</p></> : null}
    </> : null}
    {record.content_kind === 'extracted_text' ? <p className="extraction-notice">{extractionLabel(record.extraction_method)}. This is recovered source text, without an LLM-generated claim.</p> : null}
    {record.raw_values ? <dl className="fact-list">{Object.entries(record.raw_values).map(([key,value]) => <div key={key}><dt>{readable(key)}</dt><dd>{String(value ?? '')}</dd></div>)}</dl> : null}
    {!record.retrieval_eligible ? <p className="section-note">{record.evidence_scope === 'development_example' ? 'Development examples and worked answers' : 'Business context'} · searchable for inspection; excluded from assessment evidence.</p> : null}
    <details className="inspector-disclosure"><summary>Provenance</summary><dl className="fact-list">{Object.entries({ 'Evidence ID': record.evidence_id, 'Source SHA-256': record.source_sha256, Revision: record.revision, 'Evidence scope': readable(record.evidence_scope), 'Extraction model': record.extraction_model ?? (record.content_kind === 'extracted_text' ? 'Local extraction (no model)' : 'Source data'), 'Validation basis': record.validation_basis ?? record.validation_status, 'Extraction route': extractionLabel(record.extraction_method), 'Model attempts': record.extraction_attempts ?? 'Not recorded', ...(record.fallback_reason ? {'Fallback reason':record.fallback_reason} : {}) }).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl></details>
    {record.issues.length ? <details><summary>Recorded issues</summary><ul>{record.issues.map((v, i) => <li key={i}>{v}</li>)}</ul></details> : null}
  </>
}

export default function ExtractedKnowledge({ initialEvidence = '' }: { initialEvidence?: string }) {
  const [importExpanded, setImportExpanded] = useState(false)
  const [data, setData] = useState<KnowledgeInspection | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<'keyword' | 'semantic'>('keyword')
  const [category, setCategory] = useState('')
  const [source, setSource] = useState('')
  const [pageFilter, setPageFilter] = useState('')
  const [selected, setSelected] = useState(initialEvidence)
  const [previewPage, setPreviewPage] = useState('auto')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [searchAttempt, setSearchAttempt] = useState(0)
  const [hits, setHits] = useState<string[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    void fetchKnowledgeInspection(controller.signal).then(value => { if (!controller.signal.aborted) setData(value) })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Cannot load knowledge.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [attempt])
  useEffect(() => {
    if (initialEvidence) { setSelected(initialEvidence); setSource(''); setQuery(''); setMode('keyword'); setPageFilter(''); setCategory(''); setPreviewPage('auto') }
  }, [initialEvidence])
  useEffect(() => {
    const controller = new AbortController()
    setHits(null); setSearchError(''); setSearching(false)
    if (mode === 'semantic' && submittedQuery && data) {
      setSearching(true)
      void queryKnowledge({ query: submittedQuery, mode: 'qdrant', dataset: 'inspection', limit: 8, expand_synonyms: false, ...(source ? {source_id:source} : {}) }, controller.signal)
        .then(result => {
          if (controller.signal.aborted) return
          if (result.versions.inspection !== data.manifest.corpus_version) throw new Error('Knowledge has changed. Refresh records before searching.')
          setHits((result.rankings.qdrant ?? []).map(hit => hit.evidence.evidence_id))
        }).catch(reason => { if (!controller.signal.aborted) setSearchError(reason instanceof Error ? reason.message : 'Search failed.') })
        .finally(() => { if (!controller.signal.aborted) setSearching(false) })
    }
    return () => controller.abort()
  }, [submittedQuery, mode, data, searchAttempt, source])
  const records = useMemo(() => {
    let rows = data?.records.filter(r => (!source || r.source_id === source) && (!category || r.knowledge?.category === category) && (!pageFilter || (data && sourcePageFor(data,r) && sourceUnitKey(sourcePageFor(data,r)!) === pageFilter))) ?? []
    if (mode === 'keyword' && query.trim()) rows = rows.filter(r => JSON.stringify(r).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
    if (mode === 'semantic' && submittedQuery) rows = hits ? hits.flatMap(id => rows.filter(r => r.evidence_id === id)) : []
    return rows
  }, [data, source, category, pageFilter, mode, query, submittedQuery, hits])
  const record = records.find(r => r.evidence_id === selected) ?? records[0]
  const sourcePages = data?.pages.filter(p => !source || p.source_id === source) ?? []
  const page = previewPage !== 'auto' ? data?.pages.find(p => sourceUnitKey(p) === previewPage)
    : (data && record ? sourcePageFor(data, record) : sourcePages.find(p => !pageFilter || sourceUnitKey(p) === pageFilter))
  const categories = [...new Set(data?.records.filter(r => !source || r.source_id === source).flatMap(r => r.knowledge ? [r.knowledge.category] : []) ?? [])]
  return <div className="knowledge-page qwen-knowledge-page">
    <div className="knowledge-heading"><div><h1>Extracted knowledge</h1><p>{data?.manifest.sources.length ?? 0} sources · Qwen3.7 Flash with local text/OCR fallback</p></div><div className="knowledge-actions"><button type="button" className="secondary-button" aria-expanded={importExpanded} aria-controls="knowledge-import" onClick={() => setImportExpanded(value => !value)}>Add a file</button><button className="secondary-button" disabled={loading} onClick={() => setAttempt(v => v + 1)}>Refresh records</button></div></div>
    <KnowledgeImport expanded={importExpanded} onClose={() => setImportExpanded(false)} onComplete={sourceId => { setAttempt(value => value + 1); if (sourceId) { setSource(sourceId); setSelected(''); setQuery(''); setMode('keyword'); setPageFilter(''); setCategory(''); setPreviewPage('auto') } }} />
    {error ? <div role="alert" className="error-panel">{error}</div> : null}
    <div className="qwen-knowledge-grid">
      <aside className="workspace-rail records-rail" aria-label="Knowledge records">
        <div className="rail-controls"><h2>Records {data ? `(${records.length}/${data.records.length})` : ''}</h2>
          <form onSubmit={e => { e.preventDefault(); setSubmittedQuery(query.trim()); setSearchAttempt(v => v + 1) }}>
            <label htmlFor="knowledge-query">Search extracted knowledge</label><input id="knowledge-query" type="search" value={query} onChange={e => { setQuery(e.target.value); if (!e.target.value.trim()) setSubmittedQuery('') }} placeholder="Find claims or supporting text" maxLength={2000} />
            <label>Search mode<select aria-label="Search mode" value={mode} onChange={e => { setMode(e.target.value as typeof mode); setSubmittedQuery('') }}><option value="keyword">Keyword</option><option value="semantic">Semantic · BGE</option></select></label>
            {mode === 'semantic' ? <><button type="submit" className="secondary-button" disabled={searching || !query.trim()}>Search meaning</button><p className="section-note">Local similarity search over extracted knowledge and recovered source text. Top 8 matches.</p></> : null}
          </form>
          <label>Source<select aria-label="Source" value={source} onChange={e => { setSource(e.target.value); setPageFilter(''); setPreviewPage('auto'); setCategory(''); setSelected('') }}><option value="">All sources</option>{data?.manifest.sources.map(s => <option key={s.source_id} value={s.source_id}>{s.source_id} · {s.file_name}</option>)}</select></label>
          <div className="filter-pair"><label>Location<select aria-label="Record page" value={pageFilter} onChange={e => { setPageFilter(e.target.value); setPreviewPage('auto') }}><option value="">All locations</option>{sourcePages.map(p => <option key={sourceUnitKey(p)} value={sourceUnitKey(p)}>{p.source_id} · {p.label ?? `page ${p.page}`}</option>)}</select></label><label>Category<select aria-label="Category" value={category} onChange={e => setCategory(e.target.value)}><option value="">All categories</option>{categories.map(c => <option key={c} value={c}>{readable(c)}</option>)}</select></label></div>
          {mode === 'semantic' && submittedQuery && !searching && !searchError ? <p className="section-note">Results for “{submittedQuery}”</p> : null}
          {searchError ? <p role="alert">{searchError}</p> : null}
        </div>
        <div className="records-list" aria-label="Evidence records">{loading || searching ? <p role="status">{searching ? 'Searching knowledge…' : 'Loading records…'}</p> : records.length ? records.map(r => <button key={r.evidence_id} type="button" aria-pressed={record?.evidence_id === r.evidence_id} onClick={() => { setSelected(r.evidence_id); setPreviewPage('auto') }}><span><strong>{recordTitle(r)}</strong><small>{r.source_id} · {r.source_location ?? `page ${r.page}`} · {readable(r.knowledge?.category ?? r.content_kind)}</small></span></button>) : <p role="status" className="section-note">No matching records. You can still inspect the source pages.</p>}</div>
        <details className="corpus-details"><summary>Extraction details</summary>{data ? <><p>{data.records.length} records · {data.pages.length} source locations</p><p>{data.manifest.corpus_version}</p><p>Readability checks and bounded retries. No second-model scientific verification.</p><p>{data.pages.filter(p => p.extraction_method && !['qwen','unreadable'].includes(p.extraction_method)).length} locations recovered locally · {data.pages.filter(p => p.extraction_method === 'unreadable').length} unreadable</p></> : null}</details>
      </aside>
      <section className="knowledge-detail" aria-label="Selected knowledge">{record ? <RecordDetail record={record} /> : <p role="status">Select a record to inspect its extracted knowledge.</p>}</section>
      <section className="knowledge-source" aria-label="Original source page"><h2>Original source</h2><label>Source location<select aria-label="Source page" value={previewPage} onChange={e => setPreviewPage(e.target.value)}><option value="auto">Selected record location</option>{sourcePages.map(p => <option key={sourceUnitKey(p)} value={sourceUnitKey(p)}>{p.source_id} · {p.label ?? `page ${p.page}`}</option>)}</select></label>{data && page ? <SourcePreview data={data} page={page} /> : <p>No source page is available.</p>}</section>
    </div>
  </div>
}
