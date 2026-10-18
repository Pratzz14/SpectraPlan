import { displayText, readable } from '../assessment'
import type { ResolvedEvidence } from '../assessment'
import { evidenceLocation } from './AssessmentResults'
import Drawer from './Drawer'

export default function EvidenceDrawer({ evidence, claim, close }: { evidence: ResolvedEvidence; claim: string; close: () => void }) {
  return <Drawer title={evidenceLocation(evidence)} label="Evidence from this run" close={close}>
    <div className="drawer-content">
      <section><h3>Claim being inspected</h3><p>{displayText(claim)}</p></section>
      <div className="badge-group"><span className="badge">{readable(evidence.evidence_scope)}</span><span className="badge neutral">{readable(evidence.content_kind)}</span></div>
      {evidence.evidence_scope === 'research_demonstration' ? <p className="notice">Research demonstration only. This evidence does not establish clinical readiness or performance for a new application.</p> : null}
      <section><h3>{evidence.content_kind === 'figure_transcription' ? 'Figure transcription — not a verbatim quotation' : evidence.content_kind === 'method_row' ? 'Workbook-derived method row' : 'Source excerpt'}</h3><p className="evidence-text">{evidence.text}</p></section>
      {evidence.region ? <section><h3>Figure / region location</h3><p>{evidence.region.label}</p><p className="section-note">Relative page coordinates: ({evidence.region.x0}, {evidence.region.y0})–({evidence.region.x1}, {evidence.region.y1})</p></section> : null}
      {evidence.workbook_notes?.length ? <section><h3>Workbook provenance and notes</h3><ul className="result-list">{evidence.workbook_notes.map((note, i) => <li key={i}>{note.text}<span className="section-note"> · {note.sheet} row {note.row}</span></li>)}</ul></section> : null}
      <section><h3>Source details</h3><dl className="fact-list"><div><dt>Source</dt><dd>{evidenceLocation(evidence)}</dd></div><div><dt>Section</dt><dd>{evidence.section}</dd></div></dl></section>
      {evidence.issues.length ? <section><h3>Source notes</h3><ul className="result-list">{evidence.issues.map((issue, i) => <li key={i}>{displayText(issue)}</li>)}</ul></section> : null}
    </div>
  </Drawer>
}
