let tokenProvider: (() => Promise<string | null>) | null = null
let generation = 0

export function configureAuth(provider: () => Promise<string | null>) {
  tokenProvider = provider
}

export function resetRequests() { generation += 1 }

export async function apiFetch(url: string, options: RequestInit = {}) {
  if (!url.startsWith('/api/')) throw new Error('Invalid API URL.')
  const started = generation
  const token = await tokenProvider?.()
  if (started !== generation) throw new DOMException('Account changed', 'AbortError')
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(url, { ...options, headers, cache: 'no-store' })
  if (started !== generation) throw new DOMException('Account changed', 'AbortError')
  if (response.status === 401) {
    window.dispatchEvent(new Event('spectraplan:unauthorized'))
    throw new Error('Your session has expired. Sign in again.')
  }
  if (response.status === 403) throw new Error('Administrator access required.')
  return response
}
