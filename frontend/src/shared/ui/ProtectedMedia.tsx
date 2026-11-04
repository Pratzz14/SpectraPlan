import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { apiFetch } from '../api/transport'

export function ProtectedImage({ src, alt, className, onError }: { src: string; alt: string; className?: string; onError: () => void }) {
  const [loaded, setLoaded] = useState<{ src: string; url: string } | null>(null)
  const errorHandler = useRef(onError)
  useEffect(() => { errorHandler.current = onError }, [onError])
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | undefined
    void apiFetch(src, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('Image unavailable')
      const blob = await response.blob()
      if (!blob.type.startsWith('image/')) throw new Error('Unexpected image')
      if (controller.signal.aborted) return
      objectUrl = URL.createObjectURL(blob)
      setLoaded({ src, url: objectUrl })
    }).catch(() => { if (!controller.signal.aborted) errorHandler.current() })
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [src])
  return loaded?.src === src ? <img className={className} src={loaded.url} alt={alt} onError={onError} /> : <p role="status">Loading source preview…</p>
}

export function ProtectedFile({ href, children, className, download }: { href: string; children: ReactNode; className?: string; download?: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => active.current?.abort(), [])
  async function open() {
    const controller = new AbortController(); active.current = controller
    const preview = download ? null : window.open('about:blank', '_blank')
    if (preview) preview.opener = null
    setBusy(true); setError('')
    try {
      const [path, fragment] = href.split('#')
      const response = await apiFetch(path, { signal: controller.signal })
      if (!response.ok) throw new Error('File is unavailable. Please try again.')
      const blob = await response.blob()
      if (controller.signal.aborted) { preview?.close(); return }
      const url = URL.createObjectURL(blob)
      if (preview) preview.location.replace(url + (fragment ? `#${fragment}` : ''))
      else {
        const link = document.createElement('a'); link.href = url
        link.download = download || 'spectraplan-file'; document.body.append(link); link.click(); link.remove()
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (failure) {
      preview?.close()
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Unable to open file.')
    } finally { if (!controller.signal.aborted) setBusy(false) }
  }
  return <><button type="button" className={className ?? 'text-button'} disabled={busy} onClick={() => void open()}>{busy ? 'Opening…' : children}</button>{error ? <span role="alert">{error}</span> : null}</>
}
