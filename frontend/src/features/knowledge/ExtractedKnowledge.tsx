import { ProtectedFile, ProtectedImage } from '../../shared/ui/ProtectedMedia'
import { useEffect, useMemo, useState } from 'react'
import { fetchKnowledgeInspection, queryKnowledge } from '../../shared/api/api'
import type { KnowledgeInspection, KnowledgeRecord, SourcePage } from './knowledge'
import { recordTitle, sourcePageFor, sourcePageUrl, sourceUnitKey } from './knowledge'
import { readable } from '../assessment/assessment'
import KnowledgeImport from './KnowledgeImport'

const extractionLabel = (method?: string) => ({ qwen: 'Qwen extraction', pymupdf_embedded: 'Embedded PDF text · PyMuPDF', pymupdf_ocr: 'Local OCR · PyMuPDF/Tesseract', office_text: 'Original Office text', unreadable: 'No readable text recovered' }[method ?? 'qwen'] ?? method)

function SourcePreview({ data, page }: { data: KnowledgeInspection; page: SourcePage }) {
  const [failed, setFailed] = useState(false)
  const image = sourcePageUrl(data, page)
  useEffect(() => { setFailed(false) }, [image])
  const pdf = `${data.artifact_base}source/${encodeURIComponent(page.source_id)}/original${!page.format || page.format === 'pdf' ? `#page=${page.page}` : ''}`
  const isPdf = !page.format || page.format === 'pdf'
  return <>
    <div className="source-toolbar"><span>{page.source_id} · {page.label ?? `page ${page.page}`}</span><ProtectedFile href={pdf} download={isPdf ? undefined : data.manifest.sources.find(source => source.source_id === page.source_id)?.file_name}>{isPdf ? 'Open original PDF ↗' : 'Download original file ↗'}</ProtectedFile></div>
    {isPdf ? <div className="pdf-page-scroll">{image && !failed ? <ProtectedImage className="pdf-page-image" src={image} alt={`${page.source_id} original PDF page ${page.page}`} onError={() => setFailed(true)} /> : <p role="status">Source page image is unavailable. Try the original PDF link.</p>}</div> : <div className="office-source-preview">
      <p className="section-note">Source {page.format === 'workbook' ? 'cells and formulas' : 'paragraphs and table rows'}. This text preview preserves content and locations; download the original for its full formatting.</p>
      {page.rows ? <div className="source-table-scroll"><table className="source-cells"><tbody>{page.rows.map(row => <tr key={row.row}><th scope="row">{row.row}</th>{row.cells.map(cell => <td key={cell.cell}><small>{cell.cell}</small><span>{String(cell.value ?? '')}</span></td>)}</tr>)}</tbody></table></div>
        : page.blocks.map((block, i) => <div className="source-paragraph" key={i}><small>{block.location}</small><p>{block.text}</p></div>)}
    </div>}
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
    if (initialEvidence) { setSelected(initialEvidence); setSource(''); setQuery(''); setMode('keyword'); setPageFilter(''); setCategory('') }
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
  const recordIndex = record ? records.findIndex(r => r.evidence_id === record.evidence_id) : -1
  const sourcePages = data?.pages.filter(p => !source || p.source_id === source) ?? []
  const page = data && record ? sourcePageFor(data, record) : sourcePages.find(p => !pageFilter || sourceUnitKey(p) === pageFilter)
  const categories = [...new Set(data?.records.filter(r => !source || r.source_id === source).flatMap(r => r.knowledge ? [r.knowledge.category] : []) ?? [])]
  return <div className="knowledge-page qwen-knowledge-page">
    <h1 className="visually-hidden">Extracted knowledge</h1>

    <KnowledgeImport expanded={importExpanded} onClose={() => setImportExpanded(false)} onComplete={sourceId => { setAttempt(value => value + 1); if (sourceId) { setSource(sourceId); setSelected(''); setQuery(''); setMode('keyword'); setPageFilter(''); setCategory('') } }} />
    {error ? <div role="alert" className="error-panel">{error}</div> : null}
    <div className="qwen-knowledge-grid">
      <aside className="workspace-rail records-rail" aria-label="Knowledge records">
        <div className="rail-controls"><div className="records-header"><h2>Records {data ? `(${records.length}/${data.records.length})` : ''}</h2><button type="button" className="records-refresh" aria-label="Refresh records" title="Refresh records" disabled={loading} onClick={() => setAttempt(v => v + 1)}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 7a7 7 0 0 1 11.6-1L20 9M4 15l2.3 3A7 7 0 0 0 17.9 17" /></svg></button></div>
          <div className="records-actions"><button type="button" className="secondary-button" aria-expanded={importExpanded} aria-controls="knowledge-import" onClick={() => setImportExpanded(value => !value)}>Add a file</button></div>
          <form onSubmit={e => { e.preventDefault(); setSubmittedQuery(query.trim()); setSearchAttempt(v => v + 1) }}>
            <label htmlFor="knowledge-query">Search extracted knowledge</label><input id="knowledge-query" type="search" value={query} onChange={e => { setQuery(e.target.value); if (!e.target.value.trim()) setSubmittedQuery('') }} placeholder="Find claims or supporting text" maxLength={2000} />
            <label>Search mode<select aria-label="Search mode" value={mode} onChange={e => { setMode(e.target.value as typeof mode); setSubmittedQuery('') }}><option value="keyword">Keyword</option><option value="semantic">Semantic · BGE</option></select></label>
            {mode === 'semantic' ? <><button type="submit" className="secondary-button" disabled={searching || !query.trim()}>Search meaning</button><p className="section-note">Local similarity search over extracted knowledge and recovered source text. Top 8 matches.</p></> : null}
          </form>
          <label>Source<select aria-label="Source" value={source} onChange={e => { setSource(e.target.value); setPageFilter(''); setCategory(''); setSelected('') }}><option value="">All sources</option>{data?.manifest.sources.map(s => <option key={s.source_id} value={s.source_id}>{s.source_id} · {s.file_name}</option>)}</select></label>
          <div className="filter-pair"><label>Location<select aria-label="Record page" value={pageFilter} onChange={e => { setPageFilter(e.target.value) }}><option value="">All locations</option>{sourcePages.map(p => <option key={sourceUnitKey(p)} value={sourceUnitKey(p)}>{p.source_id} · {p.label ?? `page ${p.page}`}</option>)}</select></label><label>Category<select aria-label="Category" value={category} onChange={e => setCategory(e.target.value)}><option value="">All categories</option>{categories.map(c => <option key={c} value={c}>{readable(c)}</option>)}</select></label></div>
          {mode === 'semantic' && submittedQuery && !searching && !searchError ? <p className="section-note">Results for “{submittedQuery}”</p> : null}
          {searchError ? <p role="alert">{searchError}</p> : null}
        </div>
        <div className="records-list" aria-label="Evidence records">{loading || searching ? <p role="status">{searching ? 'Searching knowledge…' : 'Loading records…'}</p> : records.length ? records.map(r => <button key={r.evidence_id} type="button" aria-pressed={record?.evidence_id === r.evidence_id} onClick={() => { setSelected(r.evidence_id) }}><span><strong>{recordTitle(r)}</strong><small>{r.source_id} · {r.source_location ?? `page ${r.page}`} · {readable(r.knowledge?.category ?? r.content_kind)}</small></span></button>) : <p role="status" className="section-note">No matching records. You can still inspect the source pages.</p>}</div>
        <details className="corpus-details"><summary>Extraction details</summary>{data ? <><p>{data.records.length} records · {data.pages.length} source locations</p><p>{data.manifest.corpus_version}</p><p>Readability checks and bounded retries. No second-model scientific verification.</p><p>{data.pages.filter(p => p.extraction_method && !['qwen','unreadable'].includes(p.extraction_method)).length} locations recovered locally · {data.pages.filter(p => p.extraction_method === 'unreadable').length} unreadable</p></> : null}</details>
      </aside>
      <section className="knowledge-detail" aria-label="Selected knowledge">{record ? <><div className="record-navigation"><span>Record {recordIndex + 1} of {records.length}</span><button type="button" className="secondary-button" disabled={recordIndex >= records.length - 1} onClick={() => setSelected(records[recordIndex + 1].evidence_id)}>Next record →</button></div><RecordDetail record={record} /></> : <p role="status">Select a record to inspect its extracted knowledge.</p>}</section>
      <section className="knowledge-source" aria-label="Original source page">{data && page ? <SourcePreview data={data} page={page} /> : <p>No source page is available.</p>}</section>
    </div>
  </div>
}
