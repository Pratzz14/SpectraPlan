export interface HealthResponse {
  service: 'running'
  ready: boolean
  corpus: {
    status: 'missing' | 'unreadable' | 'invalid' | 'empty' | 'ready'
    version: string | null
    approved_passages: number
    approved_methods: number
  }
  provider: { name: 'groq'; model: string; configured: boolean }
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
    && Number.isInteger(data.corpus.approved_passages) && data.corpus.approved_passages >= 0
    && Number.isInteger(data.corpus.approved_methods) && data.corpus.approved_methods >= 0
    && !!data.provider && data.provider.name === 'groq'
    && typeof data.provider.model === 'string' && typeof data.provider.configured === 'boolean'
}
