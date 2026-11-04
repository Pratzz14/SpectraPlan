import { useNavigation } from './useNavigation'
import { lazy, Suspense, useEffect, useState } from 'react'
import AuthGate from '../features/auth/AuthGate'
import type { CurrentUser } from '../features/auth/AuthGate'
import { supabase } from '../features/auth/client'
import '../features/auth/auth.css'
const SearchWorkbench = lazy(() => import('../features/search/SearchWorkbench'))
const ExtractedKnowledge = lazy(() => import('../features/knowledge/ExtractedKnowledge'))
const AssessmentPage = lazy(() => import('../features/assessment/components/AssessmentPage'))
const WorkspaceStatus = lazy(() => import('../features/workspace/WorkspaceStatus'))
const LeadsPage = lazy(() => import('../features/leads/LeadsPage'))

export default function App() {
  return <AuthGate>{user => <Workspace key={`${user.id}:${user.role}`} user={user} />}</AuthGate>
}

function Workspace({ user }: { user: CurrentUser }) {
  const admin = user.role === 'admin'
  const [logoutError, setLogoutError] = useState('')
  async function logout() {
    const result = await supabase?.auth.signOut({ scope: 'local' })
    if (result?.error) setLogoutError('Sign out failed. Please try again.')
  }
  const { view, visited, evidenceTarget, runTarget, assessmentSession, newEnquiry } = useNavigation()
  useEffect(() => { if (!admin && view !== 'assess') window.location.hash = '#assess' }, [admin, view])
  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>Skip to content</a>
    <header className="site-header"><div className="header-inner"><a className="wordmark" href="#assess">SpectraPlan</a><nav aria-label="Main navigation">{([['assess', 'Assessment'], ['search', 'Search sources'], ['knowledge', 'Extracted knowledge'], ['leads', 'Leads'], ['workspace', 'Workspace']] as const).filter(([route]) => admin || route === 'assess').map(([route, label]) => <a key={route} href={`#${route}`} aria-current={view === route ? 'page' : undefined}>{label}</a>)}</nav><div className="account-controls"><span>{user.email}</span><button type="button" className="secondary-button" onClick={() => void logout()}>Sign out</button>{logoutError ? <p role="alert">{logoutError}</p> : null}</div></div></header>
    <Suspense fallback={<p role="status">Loading page…</p>}><main id="main-content" tabIndex={-1} className="main-content">
      <div hidden={view !== 'assess'}><AssessmentPage key={assessmentSession} initialRun={runTarget} newEnquiry={newEnquiry} /></div>
      {admin ? <div hidden={view !== 'search'}>{visited.has('search') ? <SearchWorkbench /> : null}</div> : null}
      {admin ? <div hidden={view !== 'knowledge'}>{visited.has('knowledge') ? <ExtractedKnowledge initialEvidence={evidenceTarget} /> : null}</div> : null}
      {admin ? <div hidden={view !== 'leads'}>{visited.has('leads') ? <LeadsPage active={view === 'leads'} newEnquiry={newEnquiry} /> : null}</div> : null}
      {admin ? <div hidden={view !== 'workspace'}>{visited.has('workspace') ? <WorkspaceStatus /> : null}</div> : null}
    </main></Suspense>
  </div>
}
