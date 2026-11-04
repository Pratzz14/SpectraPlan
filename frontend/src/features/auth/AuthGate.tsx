import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase, signupEnabled } from './client'
import { apiFetch, resetRequests } from '../../shared/api/transport'

export interface CurrentUser { id: string; email: string; role: 'admin' | 'customer' }

export default function AuthGate({ children }: { children: (user: CurrentUser) => ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [signup, setSignup] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (!supabase) return
    let identity: string | null | undefined
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      if (identity !== next?.user.id) {
        resetRequests(); setUser(null); identity = next?.user.id
      }
      setSession(next)
    })
    const expired = () => {
      resetRequests(); setUser(null); setSession(null)
      setError('Your session has expired. Sign in again.')
      void supabase?.auth.signOut({ scope: 'local' })
    }
    window.addEventListener('spectraplan:unauthorized', expired)
    return () => { data.subscription.unsubscribe(); window.removeEventListener('spectraplan:unauthorized', expired) }
  }, [])

  const token = session?.access_token
  const sessionId = session?.user.id
  useEffect(() => {
    if (!token || !sessionId) return
    const controller = new AbortController()
    setError('')
    void apiFetch('/api/me', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('Sign-in verification is unavailable. Try again.')
      const value: CurrentUser = await response.json()
      if (value.id !== sessionId || typeof value.email !== 'string' || !['customer', 'admin'].includes(value.role)) throw new Error('Invalid account response.')
      if (!controller.signal.aborted) setUser(value)
    }).catch(failure => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Sign-in verification failed.') })
    return () => controller.abort()
  }, [token, sessionId, retry])

  async function submit() {
    if (!supabase || busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = signup
        ? await supabase.auth.signUp({ email: email.trim(), password })
        : await supabase.auth.signInWithPassword({ email: email.trim(), password })
      if (result.error) throw result.error
      setPassword('')
      if (signup && !result.data.session) setNotice('Your account needs email confirmation. Check your inbox, or contact the administrator if email delivery is unavailable.')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Sign-in failed. Please try again.') }
    finally { setBusy(false) }
  }

  if (user && session && user.id === session.user.id) return children(user)
  return <main className="auth-page"><section className="auth-card" aria-labelledby="auth-heading">
    <a className="wordmark" href="#assess">SpectraPlan</a>
    <h1 id="auth-heading">{session ? 'Verify your account' : signup ? 'Create your account' : 'Sign in'}</h1>
    {!supabase ? <p role="alert">Sign-in is not configured. Contact the administrator.</p>
      : session === undefined ? <p role="status">Restoring your session…</p>
      : session ? <><p role="status">{error ? 'Unable to verify your account.' : 'Verifying your account…'}</p><button className="secondary-button" onClick={() => setRetry(value => value + 1)}>Retry</button><button className="secondary-button" onClick={() => void supabase?.auth.signOut({ scope: 'local' })}>Sign out</button></>
      : <><p>Use your email and password to {signup ? 'get started' : 'continue'}.</p>
        <form onSubmit={event => { event.preventDefault(); void submit() }}>
          <label htmlFor="login-email">Email</label><input id="login-email" type="email" autoComplete="email" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} />
          <label htmlFor="login-password">Password</label><input id="login-password" type="password" autoComplete={signup ? 'new-password' : 'current-password'} required minLength={signup ? 8 : 1} value={password} onChange={event => setPassword(event.target.value)} />
          {signup ? <p className="section-note">Use at least 8 characters.</p> : null}
          <button className="primary-button" disabled={busy}>{busy ? 'Please wait…' : signup ? 'Create account' : 'Sign in'}</button>
        </form>{signupEnabled ? <button className="text-button" disabled={busy} onClick={() => { setSignup(value => !value); setError(''); setNotice('') }}>{signup ? 'Already have an account? Sign in' : 'Create an account'}</button> : null}</>}
    {error ? <p role="alert" className="error-panel">{error}</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
  </section></main>
}
