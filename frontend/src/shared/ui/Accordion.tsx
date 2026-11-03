import type { ReactNode, Ref } from 'react'

export function Chevron({ up = false }: { up?: boolean }) {
  return <svg className={`chevron ${up ? 'up' : ''}`} viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m5 9 7 7 7-7" /></svg>
}

export default function Accordion({ title, description, status, open = false, warning = false, headingRef, children }: {
  title: string; description?: string; status?: string; open?: boolean; warning?: boolean;
  headingRef?: Ref<HTMLHeadingElement>; children: ReactNode;
}) {
  return <details className={`section-accordion${warning ? ' has-warning' : ''}`} open={open}>
    <summary><div><div className="accordion-title"><h2 ref={headingRef} tabIndex={headingRef ? -1 : undefined} id={headingRef ? 'decision-heading' : undefined}>{title}</h2>{status ? <span className="inline-status">{status}</span> : null}</div>{description ? <p>{description}</p> : null}</div><Chevron /></summary>
    <div className="accordion-content">{children}</div>
  </details>
}
