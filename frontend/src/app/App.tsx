import { useNavigation } from './useNavigation'
import { lazy, Suspense } from 'react'
const SearchWorkbench = lazy(() => import('../features/search/SearchWorkbench'))
const ExtractedKnowledge = lazy(() => import('../features/knowledge/ExtractedKnowledge'))
import AssessmentPage from '../features/assessment/components/AssessmentPage'
const WorkspaceStatus = lazy(() => import('../features/workspace/WorkspaceStatus'))
const HistoryPage = lazy(() => import('../features/history/HistoryPage'))

export default function App() {
  const { view, visited, evidenceTarget, runTarget, assessmentSession, setAssessmentSession } = useNavigation()
  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>Skip to content</a>
    <header className="site-header"><div className="header-inner"><a className="wordmark" href="#assess">SpectraPlan</a><nav aria-label="Main navigation">{([['assess', 'Assessment'], ['search', 'Search sources'], ['knowledge', 'Extracted knowledge'], ['history', 'History'], ['workspace', 'Workspace']] as const).map(([route, label]) => <a key={route} href={`#${route}`} aria-current={view === route ? 'page' : undefined}>{label}</a>)}</nav></div></header>
    <Suspense fallback={<p role="status">Loading page…</p>}><main id="main-content" tabIndex={-1} className="main-content">
      <div hidden={view !== 'assess'}><AssessmentPage key={assessmentSession} initialRun={runTarget} /></div>
      <div hidden={view !== 'search'}>{visited.has('search') ? <SearchWorkbench /> : null}</div>
      <div hidden={view !== 'knowledge'}>{visited.has('knowledge') ? <ExtractedKnowledge initialEvidence={evidenceTarget} /> : null}</div>
      <div hidden={view !== 'history'}>{visited.has('history') ? <HistoryPage active={view === 'history'} newEnquiry={() => { setAssessmentSession(v => v + 1); window.location.hash = '#assess' }} /> : null}</div>
      <div hidden={view !== 'workspace'}>{visited.has('workspace') ? <WorkspaceStatus /> : null}</div>
    </main></Suspense>
  </div>
}
