import assert from 'node:assert/strict'
import { test } from 'vitest'
import { fetchExplainability, fetchEnquiries, fetchEnquiry } from '../src/shared/api/api'

async function respond(value, status, work) {
  const original = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify(value), { status })
  try { return await work(new AbortController().signal) } finally { globalThis.fetch = original }
}

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
