import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { transformWithOxc } from 'vite'

async function moduleCode(name) {
  return (await transformWithOxc(await readFile(new URL(`../src/${name}.ts`, import.meta.url), 'utf8'), `${name}.ts`)).code
}
const url = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const assessmentUrl = url(await moduleCode('assessment'))
const knowledgeUrl = url(await moduleCode('knowledge'))
const apiCode = (await moduleCode('api'))
  .replace(/from ['"]\.\/assessment['"]/g, `from ${JSON.stringify(assessmentUrl)}`)
  .replace(/from ['"]\.\/knowledge['"]/g, `from ${JSON.stringify(knowledgeUrl)}`)
const { fetchGeminiComparison, fetchExplainability, fetchEnquiries, fetchEnquiry } = await import(url(apiCode))

async function respond(value, status, work) {
  const original = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify(value), { status })
  try { return await work(new AbortController().signal) } finally { globalThis.fetch = original }
}

test('optional missing comparison is distinct from malformed or failed comparison', async () => {
  assert.equal(await respond(null, 404, fetchGeminiComparison), null)
  await assert.rejects(respond({}, 503, fetchGeminiComparison), /could not be loaded/)
  await assert.rejects(respond({ model:'gemini', source_count:1, succeeded:1, results:[{ source_id:'T01',file_name:'test.xlsx',gemini:{facts:null} }] }, 200, fetchGeminiComparison), /Unexpected/)
})

test('legacy history preserves its original result without rendering an incompatible schema', async () => {
  const runId = 'a'.repeat(32)
  const saved = { run_id:runId, enquiry_id:'b'.repeat(32), draft_description:'Sample', clarification_answers:[], questions:[], events:[], run:{ old_format:true } }
  const trace = await respond(saved, 200, signal => fetchExplainability(runId, signal))
  assert.equal(trace.run, null)
  assert.deepEqual(trace.legacy_run, saved.run)
  saved.events = [null]
  await assert.rejects(respond(saved, 200, signal => fetchExplainability(runId, signal)), /Unexpected/)
})

test('history endpoints reject malformed summaries and rounds', async () => {
  await assert.rejects(respond([{ enquiry_id:'id', original_description:'Sample', rounds:1 }], 200, signal => fetchEnquiries(signal)), /Unexpected/)
  await assert.rejects(respond({ enquiry_id:'id', runs:[null] }, 200, signal => fetchEnquiry('id', signal)), /Unexpected/)
  const summary = { enquiry_id:'id', original_description:'Sample', rounds:2, latest_run_id:'latest' }
  assert.deepEqual(await respond([summary], 200, signal => fetchEnquiries(signal)), [summary])
})
