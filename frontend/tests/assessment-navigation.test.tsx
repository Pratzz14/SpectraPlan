// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import AssessmentPage from '../src/features/assessment/components/AssessmentPage'

const api = vi.hoisted(() => ({ saved: vi.fn(), enquiry: vi.fn(), assess: vi.fn(), wait: vi.fn() }))
vi.mock('../src/shared/api/api', () => ({
  fetchSavedAssessment: api.saved, fetchEnquiry: api.enquiry, assessEnquiry: api.assess, waitForAssessment: api.wait,
}))

function saved(id: string) {
  return { run_id: id, enquiry_id: `enquiry-${id}`, parent_run_id: null, run: null,
    draft_description: `Enquiry ${id}`, description: `Enquiry ${id}`,
    clarification_answers: [], status: 'interrupted' }
}

afterEach(() => { cleanup(); vi.resetAllMocks() })

test('switching saved runs clears the old enquiry and prevents submission during restoration', async () => {
  api.saved.mockResolvedValueOnce(saved('first'))
  api.enquiry.mockResolvedValue({ runs: [] })
  const { rerender } = render(<AssessmentPage initialRun="first" newEnquiry={() => {}} />)
  await waitFor(() => expect((screen.getByRole('textbox', { name: 'Customer enquiry' }) as HTMLTextAreaElement).value).toBe('Enquiry first'))
  let finish!: (value: ReturnType<typeof saved>) => void
  api.saved.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  rerender(<AssessmentPage initialRun="second" newEnquiry={() => {}} />)
  expect((screen.getByRole('textbox', { name: 'Customer enquiry' }) as HTMLTextAreaElement).value).toBe('')
  fireEvent.change(screen.getByRole('textbox', { name: 'Customer enquiry' }), { target: { value: 'Edited while loading' } })
  fireEvent.submit(screen.getByRole('textbox', { name: 'Customer enquiry' }).closest('form')!)
  expect(api.assess).not.toHaveBeenCalled()
  await act(async () => finish(saved('second')))
  await waitFor(() => expect((screen.getByRole('textbox', { name: 'Customer enquiry' }) as HTMLTextAreaElement).value).toBe('Enquiry second'))
})

test('a failed saved-run load cannot submit under the previously opened enquiry', async () => {
  api.saved.mockResolvedValueOnce(saved('first'))
  api.enquiry.mockResolvedValue({ runs: [] })
  const { rerender } = render(<AssessmentPage initialRun="first" newEnquiry={() => {}} />)
  await waitFor(() => expect((screen.getByRole('textbox', { name: 'Customer enquiry' }) as HTMLTextAreaElement).value).toBe('Enquiry first'))
  api.saved.mockRejectedValueOnce(new Error('Saved assessment unavailable'))
  rerender(<AssessmentPage initialRun="missing" newEnquiry={() => {}} />)
  await screen.findByText('Saved assessment unavailable')
  expect((screen.getByRole('textbox', { name: 'Customer enquiry' }) as HTMLTextAreaElement).value).toBe('')
  api.assess.mockRejectedValue(new Error('Offline test'))
  fireEvent.change(screen.getByRole('textbox', { name: 'Customer enquiry' }), { target: { value: 'A fresh enquiry' } })
  fireEvent.click(screen.getByRole('button', { name: 'Analyze', exact: true }))
  await waitFor(() => expect(api.assess).toHaveBeenCalledWith({
    description: 'A fresh enquiry', enquiry_id: undefined, parent_run_id: undefined,
    clarification_answers: [],
  }, expect.any(AbortSignal), expect.any(Function)))
})

 test('resumed interruption retains the saved draft and allows retry', async () => {
  api.saved.mockResolvedValueOnce({...saved('queued'), status:'queued'})
  api.wait.mockRejectedValueOnce(new Error('Assessment was interrupted'))
  render(<AssessmentPage initialRun="queued" newEnquiry={() => {}} />)
  await screen.findByText('Assessment was interrupted')
  expect((screen.getByRole('textbox', {name:'Customer enquiry'}) as HTMLTextAreaElement).value).toBe('Enquiry queued')
  fireEvent.click(screen.getByRole('button',{name:'Analyze again'}))
  await waitFor(()=>expect(api.assess).toHaveBeenCalledWith(expect.objectContaining({enquiry_id:'enquiry-queued',parent_run_id:'queued'}),expect.any(AbortSignal),expect.any(Function)))
 })
