import type { ResolvedEvidence } from './assessment'

export function evidenceLocation(evidence: ResolvedEvidence): string {
  return evidence.content_kind === 'method_row'
    ? `${evidence.source_id} · ${evidence.sheet ?? 'Workbook'}${evidence.row != null ? ` row ${evidence.row}` : ''} · underlying PDF page ${evidence.page ?? 'unknown'}`
    : `${evidence.source_id} · PDF page / slide ${evidence.page ?? 'unknown'}`
}
