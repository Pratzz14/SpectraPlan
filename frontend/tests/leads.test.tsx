// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import LeadsPage from '../src/features/leads/LeadsPage'

const api = vi.hoisted(() => ({ list: vi.fn(), detail: vi.fn(), trace: vi.fn() }))
vi.mock('../src/shared/api/api', () => ({ fetchEnquiries: api.list, fetchEnquiry: api.detail, fetchExplainability: api.trace }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

test('Leads displays customer emails, applies filters before pagination and clears selection', async () => {
  const entry = { enquiry_id: 'enquiry', customer_email: 'alice@example.test', original_description: 'Measure powder moisture', rounds: 1, updated_at: '2026-11-03T12:00:00Z' }
  api.list.mockResolvedValue(Array.from({ length: 50 }, (_, index) => ({ ...entry, enquiry_id: `enquiry-${index}` })))
  render(<LeadsPage active newEnquiry={() => {}} />)
  await screen.findAllByText('alice@example.test')
  expect(screen.getByRole('heading', { name: 'Leads' })).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Filter by email'), { target: { value: 'ALICE' } })
  fireEvent.click(screen.getByRole('button', { name: 'Filter', exact: true }))
  await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.any(AbortSignal), 0, 'ALICE'))
  await screen.findAllByText('alice@example.test')
  fireEvent.click(screen.getByRole('button', { name: 'Load older enquiries' }))
  await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.any(AbortSignal), 50, 'ALICE'))
  api.list.mockResolvedValue([])
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
  await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.any(AbortSignal), 0, ''))
  expect((screen.getByLabelText('Filter by email') as HTMLInputElement).value).toBe('')
})
