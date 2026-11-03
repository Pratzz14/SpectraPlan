import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { transformWithOxc } from 'vite'
const { code } = await transformWithOxc(await readFile(new URL('../src/knowledge.ts', import.meta.url), 'utf8'), 'knowledge.ts')
const { sourcePageUrl, sourcePageFor, sourceUnitKey, isKnowledgeInspection, recordTitle } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('source images stay inside the pinned corpus route', () => {
  const data = { artifact_base: '/api/knowledge/versions/corpus-aaaaaaaaaaaaaaaaaaaa/' }
  assert.equal(sourcePageUrl(data, { image: 'assets/page 1.jpg' }), data.artifact_base + 'assets/page%201.jpg')
  for (const image of ['../secret', 'assets/../../secret', 'https://example.test/image', '/outside', 'assets\\..\\secret']) assert.equal(sourcePageUrl(data, { image }), undefined)
  assert.equal(sourcePageUrl({ artifact_base: '/outside/' }, { image: 'safe.jpg' }), undefined)
})

test('workbook rows open their underlying source PDF page', () => {
  const page = { source_id: 'S01', page: 6 }
  assert.equal(sourcePageFor({ pages: [page] }, { source_id: 'T01', page: 1, underlying_citation: { source_id: 'S01', page: 6 } }), page)
})

test('malformed source records and review labels fail the boundary instead of crashing the inspector', () => {
  const record = { evidence_id:'S01:p1',source_id:'S01',file_name:'test.pdf',source_sha256:'a'.repeat(64),section:'Test',text:'Untrusted source text',revision:'r1',evidence_scope:'application_example',page:1,content_kind:'verbatim_text',validation_status:'passed',human_review_status:'not_reviewed',retrieval_eligible:true,issues:[] }
  const data = {artifact_base:'/api/knowledge/versions/corpus-aaaaaaaaaaaaaaaaaaaa/',manifest:{corpus_version:'corpus-aaaaaaaaaaaaaaaaaaaa',sources:[],coverage:[]},notes:[],pages:[],records:[record]}
  assert.equal(isKnowledgeInspection(data),true)
  for(const change of [r=>{delete r.records[0].human_review_status},r=>{r.records[0].facts=[{statement:'broken',quantities:null}]},r=>{r.records[0].source_spans=[{bbox:null}]},r=>{r.artifact_base='https://example.test/'}]){
    const broken=structuredClone(data);change(broken);assert.equal(isKnowledgeInspection(broken),false)
  }
})


test('Qwen records preserve structured output and reject malformed quantities', () => {
  const record = { evidence_id:'S04:p1:test',source_id:'S04',file_name:'test.pdf',source_sha256:'a'.repeat(64),section:'Test',text:'Model transcribed quote',revision:'r1',evidence_scope:'research_demonstration',page:1,content_kind:'llm_knowledge',validation_status:'passed',human_review_status:'not_reviewed',retrieval_eligible:true,issues:[],knowledge:{category:'new_model_category',claim:'Claim',support_quote:'Model transcribed quote',scope:'own_study',evidence_kind:'abstract',quantities:[{value:'a few',unit:'um',meaning:'depth'}],relevance:'Useful',caveat:null} }
  const data = {artifact_base:'/api/knowledge/versions/corpus-aaaaaaaaaaaaaaaaaaaa/',manifest:{corpus_version:'corpus-aaaaaaaaaaaaaaaaaaaa',sources:[],coverage:[]},notes:[],pages:[],records:[record]}
  assert.equal(isKnowledgeInspection(data),true)
  const broken=structuredClone(data);broken.records[0].knowledge.quantities=null
  assert.equal(isKnowledgeInspection(broken),false)
})


test('source locations distinguish identical PDF page numbers and prefer workbook cells', () => {
  const a={source_id:'S01',page:1,unit_id:'S01:p1'}, b={source_id:'S02',page:1,unit_id:'S02:p1'}, sheet={source_id:'T01',page:1,unit_id:'T01:sheet:method_comparison'}
  const data={pages:[a,b,sheet]}
  assert.notEqual(sourceUnitKey(a),sourceUnitKey(b))
  assert.equal(sourcePageFor(data,{source_id:'S02',page:1,source_unit_id:'S02:p1'}),b)
  assert.equal(sourcePageFor(data,{source_id:'T01',page:null,source_unit_id:sheet.unit_id,underlying_citation:{source_id:'S01',page:1}}),sheet)
})


test('recovered source text is inspectable without invented structured knowledge', () => {
  const record={evidence_id:'S01:p1:text',source_id:'S01',file_name:'scan.pdf',source_sha256:'a'.repeat(64),section:'Page 1',text:'Recovered spectroscopy measurements require calibration.',revision:'r1',evidence_scope:'research_demonstration',page:1,content_kind:'extracted_text',validation_status:'passed',human_review_status:'not_reviewed',retrieval_eligible:true,issues:[],extraction_method:'pymupdf_ocr',extraction_attempts:3,fallback_reason:'Incomplete model response'}
  const data={artifact_base:'/api/knowledge/versions/corpus-aaaaaaaaaaaaaaaaaaaa/',manifest:{corpus_version:'corpus-aaaaaaaaaaaaaaaaaaaa',sources:[],coverage:[]},notes:[],pages:[],records:[record]}
  assert.equal(isKnowledgeInspection(data),true)
  assert.equal(recordTitle(record),record.text)
  const broken=structuredClone(data);broken.records[0].extraction_attempts='three'
  assert.equal(isKnowledgeInspection(broken),false)
})
