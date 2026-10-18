export interface KnowledgeRecord {
  evidence_id: string; source_id: string; file_name: string; source_sha256: string; page: number | null;
  section: string; text: string; content_kind: 'verbatim_text' | 'figure_transcription' | 'method_row';
  evidence_scope: string; revision: string; validation_status: 'passed' | 'flagged';
  human_review_status: 'not_reviewed' | 'verified' | 'rejected'; retrieval_eligible: boolean; issues: string[];
  method?: string; geometry?: string; sheet?: string; row?: number;
  region?: { x0: number; y0: number; x1: number; y1: number; label: string } | null;
  source_spans?: { bbox: number[] }[];
  underlying_citation?: { source_id: string; page: number; table?: string };
  facts?: { category: string; statement: string; quantities: { label: string; value: string; unit: string | null; source_quote: string }[] }[];
  raw_values?: Record<string, unknown>;
}
export interface SourcePage {
  source_id: string; page: number; image: string; width: number; height: number;
  blocks: { text: string }[];
}
export interface KnowledgeInspection {
  artifact_base: string;
  manifest: { corpus_version: string; sources: { source_id: string; file_name: string; role: string; sha256: string; page_count: number | null }[]; coverage: unknown };
  records: KnowledgeRecord[]; pages: SourcePage[];
  notes: { sheet: string; row: number; text: string }[];
}

export function isKnowledgeInspection(value: unknown): value is KnowledgeInspection {
  const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
  const strings = (v: unknown) => Array.isArray(v) && v.every(item => typeof item === 'string');
  const region = (v: unknown) => object(v) && ['x0', 'y0', 'x1', 'y1'].every(k => typeof v[k] === 'number');
  if (!object(value) || !object(value.manifest) || typeof value.manifest.corpus_version !== 'string'
    || !/^corpus-[a-f0-9]{20}$/.test(value.manifest.corpus_version)
    || value.artifact_base !== `/api/knowledge/versions/${value.manifest.corpus_version}/`
    || !Array.isArray(value.manifest.sources) || !value.manifest.sources.every(s => object(s) && ['source_id', 'file_name', 'role', 'sha256'].every(k => typeof s[k] === 'string'))
    || !Array.isArray(value.notes) || !value.notes.every(n => object(n) && typeof n.text === 'string' && typeof n.sheet === 'string' && typeof n.row === 'number')
    || !Array.isArray(value.pages) || !value.pages.every(p => object(p) && typeof p.source_id === 'string' && typeof p.page === 'number' && typeof p.image === 'string' && typeof p.width === 'number' && typeof p.height === 'number' && Array.isArray(p.blocks) && p.blocks.every(b => object(b) && typeof b.text === 'string'))
    || !Array.isArray(value.records)) return false;
  return value.records.every(r => object(r)
    && ['evidence_id', 'source_id', 'file_name', 'source_sha256', 'section', 'text', 'revision', 'evidence_scope'].every(k => typeof r[k] === 'string')
    && (r.page === null || typeof r.page === 'number') && ['verbatim_text', 'figure_transcription', 'method_row'].includes(String(r.content_kind))
    && ['passed', 'flagged'].includes(String(r.validation_status)) && ['not_reviewed', 'verified', 'rejected'].includes(String(r.human_review_status))
    && typeof r.retrieval_eligible === 'boolean' && strings(r.issues)
    && (r.region == null || region(r.region))
    && (r.source_spans === undefined || (Array.isArray(r.source_spans) && r.source_spans.every(s => object(s) && Array.isArray(s.bbox) && s.bbox.length === 4 && s.bbox.every(v => typeof v === 'number'))))
    && (r.facts === undefined || (Array.isArray(r.facts) && r.facts.every(f => object(f) && typeof f.statement === 'string' && typeof f.category === 'string' && Array.isArray(f.quantities) && f.quantities.every(q => object(q) && typeof q.label === 'string' && typeof q.value === 'string' && typeof q.source_quote === 'string')))))
}

export function recordTitle(record: KnowledgeRecord): string {
  return record.content_kind === 'method_row' ? [record.method, record.geometry].filter(Boolean).join(' · ') || record.section : record.section;
}

export function sourcePageFor(data: KnowledgeInspection, record: KnowledgeRecord): SourcePage | undefined {
  const citation = record.underlying_citation;
  return data.pages.find(p => p.source_id === (citation?.source_id ?? record.source_id) && p.page === (citation?.page ?? record.page));
}

export function sourcePageUrl(data: KnowledgeInspection, page: SourcePage): string | undefined {
  // Images remain within the same pinned, allowlisted artifact route as the original inspection report.
  if (!/^\/api\/knowledge\/versions\/corpus-[a-f0-9]{20}\/$/.test(data.artifact_base)
    || !page.image || page.image.includes('\\') || page.image.split('/').some(part => part === '..')
    || /^[a-z]+:|^\//i.test(page.image)) return undefined;
  return data.artifact_base + page.image.split('/').map(encodeURIComponent).join('/');
}
