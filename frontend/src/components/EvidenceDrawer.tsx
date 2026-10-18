import { readable } from '../assessment'
import type { ResolvedEvidence } from '../assessment'
import { evidenceLocation } from './AssessmentResults'
import Drawer from './Drawer'

export default function EvidenceDrawer({ evidence, claim, close }: { evidence: ResolvedEvidence; claim: string; close: () => void }) {
  return <Drawer title={evidenceLocation(evidence)} label="Evidence from this run" close={close}>
    <div className="drawer-content">
      <section><h3>Claim being inspected</h3><p>{claim}</p></section>
      <div className="badge-group"><span className="badge">{readable(evidence.evidence_scope)}</span><span className="badge neutral">{readable(evidence.content_kind)}</span></div>
      {evidence.evidence_scope === 'research_demonstration' ? <p className="notice">Research demonstration only. This evidence does not establish clinical readiness or performance for a new application.</p> : null}
      <section><h3>{evidence.content_kind === 'figure_transcription' ? 'Figure transcription — not a verbatim quotation' : evidence.content_kind === 'method_row' ? 'Workbook-derived method row' : 'Source excerpt'}</h3><p className="evidence-text">{evidence.text}</p></section>
      {evidence.region ? <section><h3>Figure / region location</h3><p>{evidence.region.label}</p><p className="section-note">Relative page coordinates: ({evidence.region.x0}, {evidence.region.y0})–({evidence.region.x1}, {evidence.region.y1})</p></section> : null}
      {evidence.workbook_notes?.length ? <section><h3>Workbook provenance and notes</h3><ul className="result-list">{evidence.workbook_notes.map((note, i) => <li key={i}>{note.text}<span className="section-note"> · {note.sheet} row {note.row}</span></li>)}</ul></section> : null}
      <section><h3>Source and review status</h3><dl className="fact-list"><div><dt>Filename</dt><dd>{evidence.file_name}</dd></div><div><dt>Section</dt><dd>{evidence.section}</dd></div><div><dt>Automated validation</dt><dd>{readable(evidence.validation_status)}</dd></div><div><dt>Human review</dt><dd>{readable(evidence.human_review_status)}</dd></div><div><dt>Evidence ID</dt><dd>{evidence.evidence_id}</dd></div><div><dt>Corpus version</dt><dd>{evidence.corpus_version}</dd></div><div><dt>Revision</dt><dd>{evidence.revision}</dd></div><div><dt>Source SHA-256</dt><dd>{evidence.source_sha256}</dd></div></dl></section>
      {evidence.issues.length ? <section><h3>Recorded issues</h3><ul className="result-list">{evidence.issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul></section> : null}
      <p className="section-note">Automated validation and human review are separate labels. Neither establishes AFS approval or suitability for your application.</p>
    </div>
  </Drawer>
}
