// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Session } from '@supabase/supabase-js'
import AuthGate from '../src/features/auth/AuthGate'
import { apiFetch, configureAuth, resetRequests } from '../src/shared/api/transport'

const mock = vi.hoisted(() => ({
  listener: null as null | ((event: string, session: unknown) => void),
  signIn: vi.fn(), signup: vi.fn(), signOut: vi.fn(),
}))
vi.mock('../src/features/auth/client', () => ({ supabase: { auth: {
  onAuthStateChange: (callback: typeof mock.listener) => {
    mock.listener = callback
    queueMicrotask(() => callback?.('INITIAL_SESSION', null))
    return { data: { subscription: { unsubscribe: vi.fn() } } }
  },
  signInWithPassword: mock.signIn,
  signUp: mock.signup,
  signOut: mock.signOut,
} } }))

const customer = { id: 'customer', email: 'customer@example.test', role: 'customer' }
const session = (id = 'customer') => ({ access_token: `token-${id}`, user: { id } }) as Session

beforeEach(() => {
  configureAuth(async () => null)
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(customer))))
  mock.signIn.mockResolvedValue({ error: null, data: {} })
  mock.signup.mockResolvedValue({ error: null, data: {} })
  mock.signOut.mockImplementation(async () => { mock.listener?.('SIGNED_OUT', null); return { error: null } })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); resetRequests() })

test('email/password sign-in errors and account creation are visible', async () => {
  render(<AuthGate>{user => <p>Welcome {user.email}</p>}</AuthGate>)
  await screen.findByRole('button', { name: 'Sign in' })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'customer@example.test' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password123' } })
  mock.signIn.mockResolvedValue({ error: new Error('Invalid login credentials') })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Invalid login credentials')
  expect(mock.signIn).toHaveBeenCalledWith({ email: 'customer@example.test', password: 'password123' })
  fireEvent.click(screen.getByRole('button', { name: 'Create an account' }))
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect((await screen.findByRole('status')).textContent).toContain('needs email confirmation')
  expect(mock.signup).toHaveBeenCalled()
})

test('only verified backend identity renders the workspace and expiry clears it', async () => {
  render(<AuthGate>{user => <p>Welcome {user.email}</p>}</AuthGate>)
  await screen.findByRole('button', { name: 'Sign in' })
  act(() => mock.listener?.('SIGNED_IN', session()))
  await screen.findByText('Welcome customer@example.test')
  act(() => window.dispatchEvent(new Event('spectraplan:unauthorized')))
  await screen.findByRole('button', { name: 'Sign in' })
  expect(screen.queryByText('Welcome customer@example.test')).toBeNull()
  expect(mock.signOut).toHaveBeenCalledWith({ scope: 'local' })
})

test('account change removes previous workspace while verification is pending', async () => {
  render(<AuthGate>{user => <p>Welcome {user.email}</p>}</AuthGate>)
  await screen.findByRole('button', { name: 'Sign in' })
  act(() => mock.listener?.('SIGNED_IN', session()))
  await screen.findByText('Welcome customer@example.test')
  vi.mocked(fetch).mockImplementation(() => new Promise(() => {}))
  act(() => mock.listener?.('SIGNED_IN', session('other')))
  expect(screen.queryByText('Welcome customer@example.test')).toBeNull()
  await screen.findByText('Verifying your account…')
})

test('backend outage offers retry without exposing workspace', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response('{}', { status: 503 }))
  render(<AuthGate>{() => <p>Private workspace</p>}</AuthGate>)
  await screen.findByRole('button', { name: 'Sign in' })
  act(() => mock.listener?.('SIGNED_IN', session()))
  expect((await screen.findByRole('alert')).textContent).toContain('unavailable')
  expect(screen.queryByText('Private workspace')).toBeNull()
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(customer)))
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await screen.findByText('Private workspace')
})

test('authenticated transport sends bearer headers and discards prior-account responses', async () => {
  configureAuth(async () => 'test-token')
  await apiFetch('/api/me')
  expect(new Headers(vi.mocked(fetch).mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer test-token')
  let finish!: (response: Response) => void
  vi.mocked(fetch).mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const pending = apiFetch('/api/enquiries')
  await waitFor(() => expect(finish).toBeDefined())
  resetRequests()
  finish(new Response('[]'))
  await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
})
