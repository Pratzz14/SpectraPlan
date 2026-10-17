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
  provider: { name: 'groq' | 'llmtech'; model: string; configured: boolean }
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
    && !!data.provider && ['groq', 'llmtech'].includes(data.provider.name)
    && typeof data.provider.model === 'string' && typeof data.provider.configured === 'boolean'
}
