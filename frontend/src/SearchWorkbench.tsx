import ExternalLinkIcon from './components/ExternalLinkIcon'
import { useEffect, useRef, useState } from 'react'
import { fetchSearchStatus, queryKnowledge, resolveSearchEvidence } from './api'
import type { SearchDataset, SearchHit, SearchMode, SearchResponse, SearchStatus } from './api'
import type { ResolvedEvidence } from './assessment'
import { readable } from './assessment'
import EvidenceDrawer from './components/EvidenceDrawer'
import Drawer from './components/Drawer'

const modes = [{value:'compare',label:'Compare all'},{value:'bm25',label:'BM25 keywords'},{value:'qdrant',label:'Qdrant semantic'},{value:'hybrid',label:'Hybrid'}] as const
const datasetLabels = { technical: 'Technical corpus', website: 'Website context', all: 'Technical + website context', inspection: 'All extracted knowledge' }
const engines = {bm25:{title:'BM25',score:'BM25 score'},qdrant:{title:'Qdrant',score:'Cosine similarity'},hybrid:{title:'Hybrid',score:'RRF score'}}
function safeUrl(value?: string) { try { const url=new URL(value ?? ''); return url.protocol==='https:' ? url.href : undefined } catch { return undefined } }

function ResultRow({hit, engine, inspect}: {hit:SearchHit;engine:keyof typeof engines;inspect:(hit:SearchHit)=>void}) {
  const e=hit.evidence
  return <article className="search-result-row"><div className="rank-number">{hit.rank}</div><div className="rank-content"><h3>{e.knowledge?.claim ?? e.section}</h3><p className="source-locator">{e.dataset==='website' ? e.page_title : `${e.source_id} · ${e.source_location ?? (e.content_kind==='method_row' ? `${e.sheet} row ${e.row}` : e.page ? `Page ${e.page}` : e.section)}`} · {readable(e.evidence_scope)}</p>
    <p className="search-excerpt">{e.text}</p><div className="search-result-actions"><button className="text-button" type="button" onClick={()=>inspect(hit)}>Inspect evidence <ExternalLinkIcon /></button>{e.dataset !== 'website' ? <a className="text-button" href={`#knowledge?evidence=${encodeURIComponent(e.evidence_id)}`}>View original source <ExternalLinkIcon /></a> : null}</div>
    <details className="score-details"><summary>Scores and provenance</summary><p>{engines[engine].score}: {hit.score.toFixed(engine==='hybrid'?5:4)}</p><p>Found by: {hit.branches.join(' + ')}</p>{hit.matched_terms.length ? <p>Matched terms: {hit.matched_terms.join(', ')}</p>:null}<dl className="fact-list"><div><dt>Evidence ID</dt><dd>{e.evidence_id}</dd></div><div><dt>Revision</dt><dd>{e.revision}</dd></div><div><dt>Source SHA-256</dt><dd>{e.source_sha256}</dd></div></dl><p>Scores express relevance within this method, not confidence percentages.</p>{hit.matching_segment ? <p>{hit.matching_segment}</p>:null}</details>
  </div></article>
}

export default function SearchWorkbench() {
  const [status,setStatus]=useState<SearchStatus|null>(null)
  const [query,setQuery]=useState('')
  const [mode,setMode]=useState<SearchMode>('compare')
  const [dataset,setDataset]=useState<SearchDataset>('technical')
  const [limit,setLimit]=useState(6)
  const [expand,setExpand]=useState(true)
  const [result,setResult]=useState<SearchResponse|null>(null)
  const [error,setError]=useState<string|null>(null)
  const [statusError,setStatusError]=useState<string|null>(null)
  const [loading,setLoading]=useState(false)
  const [evidenceLoading,setEvidenceLoading]=useState(false)
  const [selectedClaim,setSelectedClaim]=useState('')
  const [technical,setTechnical]=useState<ResolvedEvidence|null>(null)
  const [website,setWebsite]=useState<SearchHit|null>(null)
  const active=useRef<AbortController|null>(null)
  const evidenceRequest=useRef<AbortController|null>(null)
  useEffect(()=>{
    const controller=new AbortController()
    void fetchSearchStatus(controller.signal).then(setStatus).catch(()=>{if(!controller.signal.aborted)setStatusError('Dataset status is unavailable.')})
    return ()=>{controller.abort();active.current?.abort();active.current=null;evidenceRequest.current?.abort();evidenceRequest.current=null}
  },[])
  async function submit() {
    if(!query.trim())return
    active.current?.abort();evidenceRequest.current?.abort();evidenceRequest.current=null
    const controller=new AbortController();active.current=controller
    setLoading(true);setError(null);setResult(null);setTechnical(null);setWebsite(null);setEvidenceLoading(false)
    const timeout=window.setTimeout(()=>controller.abort('timeout'),120000)
    try {
      const response=await queryKnowledge({query:query.trim(),mode,dataset,limit,expand_synonyms:expand},controller.signal)
      if(active.current===controller&&!controller.signal.aborted)setResult(response)
    }catch(failure){if(active.current===controller)setError(controller.signal.aborted?'Search timed out. Retry or choose BM25.':failure instanceof Error?failure.message:'Search is unavailable.')}
    finally{window.clearTimeout(timeout);if(active.current===controller)setLoading(false)}
  }
  async function inspect(hit:SearchHit) {
    setSelectedClaim(hit.evidence.knowledge?.claim ?? hit.evidence.section)
    evidenceRequest.current?.abort();evidenceRequest.current=null;setError(null);setTechnical(null);setWebsite(null)
    if(hit.evidence.dataset==='website'){setWebsite(hit);setEvidenceLoading(false);return}
    const version=result?.versions.technical
    if(!version){setError('The search did not supply a corpus version. Run it again.');return}
    const controller=new AbortController();evidenceRequest.current=controller;setEvidenceLoading(true)
    try{const value=await resolveSearchEvidence(hit.evidence.evidence_id,version,hit.evidence.revision,controller.signal);if(evidenceRequest.current===controller&&!controller.signal.aborted)setTechnical(value)}
    catch(failure){if(evidenceRequest.current===controller&&!controller.signal.aborted)setError(failure instanceof Error?failure.message:'Cannot open evidence.')}
    finally{if(evidenceRequest.current===controller)setEvidenceLoading(false)}
  }
  function download() {
    if(!result||loading)return
    const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}))
    const link=document.createElement('a');link.href=url;link.download='spectraplan-search.json';document.body.append(link);link.click();link.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  return <div className="split-workspace search-workspace">
    <form className="workspace-rail search-controls" onSubmit={event=>{event.preventDefault();void submit()}}><h1>Search sources</h1>
      <label htmlFor="source-search-query">Query</label><textarea id="source-search-query" value={query} onChange={e=>setQuery(e.target.value)} maxLength={2000} rows={3}/>
      <label>Dataset<select aria-label="Dataset" value={dataset} onChange={e=>setDataset(e.target.value as SearchDataset)}><option value="technical">Technical corpus</option><option value="website">Website context</option><option value="all">Technical + website context</option></select></label>
      <label>Method<select aria-label="Method" value={mode} onChange={e=>setMode(e.target.value as SearchMode)}>{modes.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <label>Results per method<select aria-label="Results per method" value={limit} onChange={e=>setLimit(Number(e.target.value))}>{[4,6,8].map(n=><option key={n}>{n}</option>)}</select></label>
      <label className="checkbox-label"><input type="checkbox" checked={expand} onChange={e=>setExpand(e.target.checked)}/>Expand synonyms</label>
      <details className="dataset-details"><summary>Dataset details</summary>{statusError?<p>{statusError}</p>:null}{status?<><p>Technical: {status.technical.status} · {status.technical.records} records</p><p>Website: {status.website.status} · {status.website.records} records</p>{status.website.fetched_at?<p>Snapshot: {new Date(status.website.fetched_at).toLocaleString()}</p>:null}{status.website.seed_url?<a href={safeUrl(status.website.seed_url)} target="_blank" rel="noreferrer">Website source</a>:null}<p className="version-text">{status.technical.corpus_version}</p></>:<p>Loading status…</p>}</details>
      <button type="submit" className="primary-button" disabled={!query.trim()||loading}>{loading?'Searching…':'Search'}</button><p className="section-note">Search runs locally. Website results are business context.</p>
    </form>
    <section className="workspace-results search-output" aria-label="Search results" aria-busy={loading}><div className="results-toolbar"><h2>Results</h2>{result?<span>{result.mode==='compare'?'Compare all':engines[result.mode].title}</span>:null}</div>
      <div className="result-scroll">{loading?<p role="status" className="compact-notice">Searching…</p>:null}{error?<p role="alert" className="error-panel">{error}</p>:null}{evidenceLoading?<p role="status" className="compact-notice">Loading evidence…</p>:null}
        {result?<><p className="result-query">Results for “{result.query}” · {datasetLabels[result.dataset]}</p>{result.warnings.map(w=><p key={w} className="compact-notice warning">{w}</p>)}<div className={`ranking-columns ${result.mode==='compare'?'compare':''}`}>{(Object.keys(result.rankings) as (keyof typeof engines)[]).map(engine=><section className="ranking-column" key={engine} aria-label={`${engines[engine].title} results`}><h2>{engines[engine].title}</h2>{result.rankings[engine]?.length?result.rankings[engine]!.map(hit=><ResultRow key={hit.evidence.evidence_id} hit={hit} engine={engine} inspect={hit=>void inspect(hit)}/>):<p className="section-note">No matches. Try another query.</p>}</section>)}</div><details className="search-run-details"><summary>Search details</summary><p>{result.elapsed_ms.toFixed(0)} ms · {result.dataset} · {result.model_calls} model calls</p>{result.expanded_terms.length?<p>Expanded terms: {result.expanded_terms.join(', ')}</p>:null}<pre>{JSON.stringify(result.versions,null,2)}</pre></details></>:!loading?<p className="empty-workspace">Enter a query to inspect matching evidence.</p>:null}
      </div><footer className="workspace-footer"><button type="button" className="secondary-button" disabled={!result||loading} onClick={download}>Download search JSON</button></footer>
    </section>
    {technical?<EvidenceDrawer evidence={technical} claim={selectedClaim} label="Search evidence" close={()=>setTechnical(null)}/>:null}
    {website?<Drawer title={website.evidence.page_title??website.evidence.section} close={()=>setWebsite(null)}><div className="drawer-content"><p className="notice">Website · business context</p><p className="evidence-text">{website.evidence.text}</p>{safeUrl(website.evidence.location_url??website.evidence.url)?<a href={safeUrl(website.evidence.location_url??website.evidence.url)} target="_blank" rel="noreferrer">Open website source</a>:null}<dl className="fact-list"><div><dt>Evidence ID</dt><dd>{website.evidence.evidence_id}</dd></div><div><dt>Snapshot</dt><dd>{website.evidence.fetched_at}</dd></div><div><dt>Source SHA-256</dt><dd>{website.evidence.source_sha256}</dd></div><div><dt>Source check</dt><dd>{website.evidence.validation_basis}</dd></div></dl></div></Drawer>:null}
  </div>
}
