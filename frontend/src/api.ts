import { isAssessmentRun } from './assessment'
import type { AssessmentRequest, AssessmentRun, ExplainabilityTrace, EnquirySummary, EnquiryDetail, ResolvedEvidence } from './assessment'
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

export interface GeminiComparison {
  model: string
  source_count: number
  succeeded: number
  errors: number
  comparison_note?: string
  results: {
    source_id: string
    file_name: string
    gemini: { claims: string[]; facts: string[]; unknowns: string[]; source_locations: string[] } | null
    error: { code: string; message: string } | null
  }[]
}

export async function fetchGeminiComparison(signal: AbortSignal): Promise<GeminiComparison | null> {
  const response = await fetch('/api/knowledge/gemini-comparison', { signal, cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error('Gemini comparison could not be loaded.')
  const data = await response.json() as GeminiComparison
  if (!data || typeof data.model !== 'string' || !Number.isInteger(data.succeeded) || !Number.isInteger(data.source_count)
    || !Array.isArray(data.results) || !data.results.every(r => r && typeof r.source_id === 'string' && typeof r.file_name === 'string'
      && (r.gemini === null || (r.gemini && ['facts', 'claims', 'unknowns', 'source_locations'].every(k =>
        Array.isArray(r.gemini![k as keyof typeof r.gemini]) && (r.gemini![k as keyof typeof r.gemini] as string[]).every(v => typeof v === 'string')))))) {
    throw new Error('Unexpected Gemini comparison response.')
  }
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

export async function fetchExplainability(runId: string, signal: AbortSignal): Promise<ExplainabilityTrace> {
  const response = await fetch(`/api/assess/${encodeURIComponent(runId)}/explainability`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error(`Explainability trace could not be loaded (HTTP ${response.status}).`)
  const data = await response.json() as ExplainabilityTrace
  if (!data || data.run_id !== runId || !Array.isArray(data.events) || !data.events.every(e => e && typeof e.stage === 'string'
    && typeof e.event_type === 'string' && typeof e.created_at === 'string' && Number.isInteger(e.sequence)
    && e.payload && typeof e.payload === 'object') || !Array.isArray(data.clarification_answers) || !Array.isArray(data.questions)
    || typeof data.enquiry_id !== 'string' || typeof data.draft_description !== 'string') throw new Error('Unexpected explainability response.')
  if (data.run !== null && !isAssessmentRun(data.run)) return { ...data, legacy_run: data.run, run: null }
  return data
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
    name: 'auto' | 'gemini' | 'groq' | 'llmtech'; model: string; configured: boolean
    mode: 'auto' | 'gemini' | 'groq' | 'llmtech'; selected: string | null
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
    && !!data.provider && ['auto', 'gemini', 'groq', 'llmtech'].includes(data.provider.name)
    && typeof data.provider.model === 'string' && typeof data.provider.configured === 'boolean'
    && ['auto', 'gemini', 'groq', 'llmtech'].includes(data.provider.mode)
    && (data.provider.selected === null || typeof data.provider.selected === 'string')
    && Array.isArray(data.provider.candidates)
    && data.provider.candidates.every(p => !!p && typeof p.name === 'string' && typeof p.configured === 'boolean'
      && ['unchecked', 'working', 'unavailable', 'not_configured'].includes(p.status))
}

export type SearchMode = 'compare' | 'bm25' | 'qdrant' | 'hybrid'
export type SearchDataset = 'technical' | 'website' | 'all' | 'inspection'
export interface SearchEvidence {
  source_location?: string; knowledge?: { claim: string };
  evidence_id: string; section: string; text: string; source_id: string; content_kind: string;
  evidence_scope: string; dataset: 'technical' | 'website' | 'inspection'; page?: number; sheet?: string; row?: number;
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

export async function queryKnowledge(input: {query: string; mode: SearchMode; dataset: SearchDataset; limit: number; expand_synonyms: boolean; source_id?: string}, signal: AbortSignal): Promise<SearchResponse> {
  const response = await fetch('/api/search', {method: 'POST', signal, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(input)})
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Search failed. Check your query and dataset readiness.')
  if (typeof data.query !== 'string' || !data.rankings || !Array.isArray(data.warnings)) throw new Error('Unexpected search response.')
  return data as SearchResponse
}

export async function fetchEnquiries(signal: AbortSignal, offset = 0): Promise<EnquirySummary[]> {
  const response = await fetch(`/api/enquiries?limit=50&offset=${offset}`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('Saved enquiries could not be loaded.')
  const data = await response.json() as EnquirySummary[]
  if (!Array.isArray(data) || !data.every(e => e && typeof e.enquiry_id === 'string' && typeof e.original_description === 'string'
    && typeof e.latest_run_id === 'string' && Number.isInteger(e.rounds))) throw new Error('Unexpected enquiry history response.')
  return data
}

export async function fetchEnquiry(enquiryId: string, signal: AbortSignal): Promise<EnquiryDetail> {
  const response = await fetch(`/api/enquiries/${encodeURIComponent(enquiryId)}`, { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('Saved enquiry could not be opened.')
  const data = await response.json() as EnquiryDetail
  if (!data || data.enquiry_id !== enquiryId || !Array.isArray(data.runs) || !data.runs.every(r => r && typeof r.run_id === 'string'
    && typeof r.status === 'string' && Number.isInteger(r.round_no))) throw new Error('Unexpected enquiry response.')
  return data
}

export interface KnowledgeIngestion {
  job_id: string
  status: 'idle' | 'queued' | 'running' | 'succeeded' | 'failed' | 'prepared'
  filename?: string
  source_id?: string
  message?: string
  qwen_configured?: boolean
  endpoint_host?: string
  max_bytes?: number
  progress?: { completed?: number; total?: number; failed?: number; records?: number; fallback?: number; unreadable?: number }
}

function ingestionResponse(value: unknown): KnowledgeIngestion {
  if (!value || typeof value !== 'object' || !('status' in value) || !('job_id' in value)
    || typeof value.job_id !== 'string' || !['idle','queued','running','succeeded','failed','prepared'].includes(String(value.status))) throw new Error('Unexpected ingestion status.')
  return value as KnowledgeIngestion
}

export async function fetchKnowledgeIngestion(signal: AbortSignal): Promise<KnowledgeIngestion> {
  const response = await fetch('/api/knowledge/ingest/status', { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('Could not load ingestion progress.')
  return ingestionResponse(await response.json())
}

export async function uploadKnowledgeFile(file: File, role: string): Promise<KnowledgeIngestion> {
  const query = new URLSearchParams({ filename: file.name, role })
  const response = await fetch(`/api/knowledge/ingest?${query}`, {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
  })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Upload failed (HTTP ${response.status}).`)
  return ingestionResponse(data)
}
