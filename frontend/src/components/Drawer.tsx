import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

export default function Drawer({ title, label = 'Source evidence', close, children }: { title: string; label?: string; close: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const element = dialog.current
    element?.showModal(); closeButton.current?.focus()
    return () => { element?.close(); if (previous?.isConnected) previous.focus() }
  }, [])
  return <dialog ref={dialog} className="evidence-drawer" aria-labelledby="evidence-title" onCancel={event => { event.preventDefault(); close() }} onKeyDown={event => {
    if (event.key !== 'Tab') return
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], summary, [tabindex="0"]')).filter(el => el.getClientRects().length)
    const first = controls[0], last = controls.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }}><div className="drawer-heading"><div><p className="eyebrow">{label}</p><h2 id="evidence-title">{title}</h2></div><button ref={closeButton} type="button" className="secondary-button" onClick={close}>Close evidence</button></div>{children}</dialog>
}
