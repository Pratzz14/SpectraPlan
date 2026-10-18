import { isAssessmentRun } from './assessment'
import type { AssessmentRequest, AssessmentRun, ResolvedEvidence } from './assessment'
import type { KnowledgeInspection } from './knowledge'
import { isKnowledgeInspection } from './knowledge'
export type { AssessmentRequest, AssessmentRun } from './assessment'

export async function resolveSearchEvidence(id: string, version: string, revision: string, signal: AbortSignal): Promise<ResolvedEvidence> {
  const response = await fetch(`/api/evidence/${encodeURIComponent(id)}?${new URLSearchParams({ corpus_version: version, revision })}`, { signal })
  if (!response.ok) throw new Error(`Evidence could not be opened (HTTP ${response.status}). Retry the search if the corpus has changed.`)
  const data = await response.json() as ResolvedEvidence
  if (data.evidence_id !== id || data.revision !== revision || data.corpus_version !== version || typeof data.text !== 'string'
    || !Array.isArray(data.issues) || typeof data.file_name !== 'string') throw new Error('Evidence response does not match this search result.')
  return data
}

export async function fetchKnowledgeInspection(signal: AbortSignal): Promise<KnowledgeInspection> {
  const response = await fetch('/api/knowledge/inspection', { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('Extracted knowledge is unavailable. Check workspace status, then retry.')
  const data: unknown = await response.json()
  if (!isKnowledgeInspection(data)) throw new Error('Unexpected knowledge inspection response.')
  return data
}

export async function assessEnquiry(input: AssessmentRequest, signal: AbortSignal): Promise<AssessmentRun> {
  let response: Response
  try {
    response = await fetch('/api/assess', {
      method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new Error('Cannot reach the assessment service. Check the backend connection and try again.')
  }
  let data: unknown
  try { data = await response.json() } catch {
    throw new Error(`The assessment service returned an unreadable response (HTTP ${response.status}). Please try again.`)
  }
  // F06 can return a valid incomplete envelope on non-2xx responses.
  if (isAssessmentRun(data) && (response.ok || ([502, 503, 504].includes(response.status) && data.run_status === 'incomplete'))) return data
  if (response.status === 422) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null
    const message = detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string' ? detail.message : null
    throw new Error(message ?? 'The enquiry was not accepted. Check that it contains text and is within the service’s length limit, then submit again.')
  }
  if (!response.ok) throw new Error(`The assessment service failed (HTTP ${response.status}). Please try again or check workspace status.`)
  throw new Error('Unexpected assessment response. No result was displayed. Please try again or check the backend version.')
}

export interface HealthResponse {
  service: 'running'
  ready: boolean
  corpus: {
    status: 'missing' | 'unreadable' | 'invalid' | 'empty' | 'ready'
    version: string | null
    eligible_passages: number
    eligible_methods: number
    flagged_records: number
    human_verified_records: number
  }
  provider: {
    name: 'auto' | 'groq' | 'llmtech'; model: string; configured: boolean
    mode: 'auto' | 'groq' | 'llmtech'; selected: string | null
    candidates: { name: string; configured: boolean; status: 'unchecked' | 'working' | 'unavailable' | 'not_configured'; error_code: string | null }[]
  }
}

export async function fetchHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('Backend readiness is unavailable.')
  const data: unknown = await response.json()
  // Guard the boundary so a wrong service/proxy response becomes a visible error.
  if (!isHealthResponse(data)) throw new Error('Unexpected backend readiness response.')
  return data
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (!value || typeof value !== 'object') return false
  const data = value as Partial<HealthResponse>
  return data.service === 'running' && typeof data.ready === 'boolean'
    && !!data.corpus && ['missing', 'unreadable', 'invalid', 'empty', 'ready'].includes(data.corpus.status)
    && (data.corpus.version === null || typeof data.corpus.version === 'string')
    && Number.isInteger(data.corpus.eligible_passages) && data.corpus.eligible_passages >= 0
    && Number.isInteger(data.corpus.eligible_methods) && data.corpus.eligible_methods >= 0
    && Number.isInteger(data.corpus.flagged_records) && data.corpus.flagged_records >= 0
    && Number.isInteger(data.corpus.human_verified_records) && data.corpus.human_verified_records >= 0
    && !!data.provider && ['auto', 'groq', 'llmtech'].includes(data.provider.name)
    && typeof data.provider.model === 'string' && typeof data.provider.configured === 'boolean'
    && ['auto', 'groq', 'llmtech'].includes(data.provider.mode)
    && (data.provider.selected === null || typeof data.provider.selected === 'string')
    && Array.isArray(data.provider.candidates)
    && data.provider.candidates.every(p => !!p && typeof p.name === 'string' && typeof p.configured === 'boolean'
      && ['unchecked', 'working', 'unavailable', 'not_configured'].includes(p.status))
}

export type SearchMode = 'compare' | 'bm25' | 'qdrant' | 'hybrid'
export type SearchDataset = 'technical' | 'website' | 'all'
export interface SearchEvidence {
  evidence_id: string; section: string; text: string; source_id: string; content_kind: string;
  evidence_scope: string; dataset: 'technical' | 'website'; page?: number; sheet?: string; row?: number;
  url?: string; location_url?: string; page_title?: string; fetched_at?: string; revision: string;
  source_sha256: string; selector?: string; human_review_status: string; validation_basis?: string;
}
export interface SearchHit {
  rank: number; score: number; bm25_score: number | null; qdrant_score: number | null;
  branches: string[]; matched_terms: string[]; matching_segment: string | null; evidence: SearchEvidence;
}
export interface SearchResponse {
  query: string; mode: SearchMode; dataset: SearchDataset; versions: Record<string, string>;
  elapsed_ms: number; query_terms: string[]; expanded_terms: string[];
  rankings: Partial<Record<'bm25' | 'qdrant' | 'hybrid', SearchHit[]>>; warnings: string[]; model_calls: number;
}
export interface DatasetStatus { status: 'ready' | 'unavailable'; records: number; corpus_version?: string; pages?: number; seed_url?: string; fetched_at?: string }
export interface SearchStatus { technical: DatasetStatus; website: DatasetStatus }

export async function fetchSearchStatus(signal: AbortSignal): Promise<SearchStatus> {
  const response = await fetch('/api/search/status', {signal, cache: 'no-store'})
  if (!response.ok) throw new Error('Search status is unavailable.')
  return response.json() as Promise<SearchStatus>
}

export async function queryKnowledge(input: {query: string; mode: SearchMode; dataset: SearchDataset; limit: number; expand_synonyms: boolean}, signal: AbortSignal): Promise<SearchResponse> {
  const response = await fetch('/api/search', {method: 'POST', signal, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(input)})
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Search failed. Check your query and dataset readiness.')
  if (typeof data.query !== 'string' || !data.rankings || !Array.isArray(data.warnings)) throw new Error('Unexpected search response.')
  return data as SearchResponse
}
