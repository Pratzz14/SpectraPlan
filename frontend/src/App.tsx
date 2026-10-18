import { useEffect, useState } from 'react'
import SearchWorkbench from './SearchWorkbench'
import ExtractedKnowledge from './ExtractedKnowledge'
import AssessmentPage from './components/AssessmentPage'
import WorkspaceStatus from './components/WorkspaceStatus'
import HistoryPage from './components/HistoryPage'

type View = 'assess' | 'search' | 'knowledge' | 'history' | 'workspace'
function currentView(): View {
  const route = window.location.hash.split('?')[0]
  return route === '#history' ? 'history' : route === '#search' ? 'search' : route === '#knowledge' ? 'knowledge' : ['#workspace', '#status'].includes(route) ? 'workspace' : 'assess'
}

export default function App() {
  const [view, setView] = useState(currentView)
  const [visited, setVisited] = useState(() => new Set<View>([currentView()]))
  const [evidenceTarget, setEvidenceTarget] = useState(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('evidence') ?? '')
  const [runTarget, setRunTarget] = useState(() => currentView() === 'assess' ? new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('run') ?? '' : '')
  const [assessmentSession, setAssessmentSession] = useState(0)
  useEffect(() => {
    const update = () => {
      const next = currentView(); setRunTarget(next === 'assess' ? new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('run') ?? '' : ''); setView(next); setVisited(value => new Set([...value, next]))
      setEvidenceTarget(new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('evidence') ?? '')
    }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>Skip to content</a>
    <header className="site-header"><div className="header-inner"><a className="wordmark" href="#assess">SpectraPlan</a><nav aria-label="Main navigation">{([['assess', 'Assessment'], ['search', 'Search sources'], ['knowledge', 'Extracted knowledge'], ['history', 'History'], ['workspace', 'Workspace']] as const).map(([route, label]) => <a key={route} href={`#${route}`} aria-current={view === route ? 'page' : undefined}>{label}</a>)}</nav></div></header>
    <main id="main-content" tabIndex={-1} className="main-content">
      <div hidden={view !== 'assess'}><AssessmentPage key={assessmentSession} initialRun={runTarget} /></div>
      <div hidden={view !== 'search'}>{visited.has('search') ? <SearchWorkbench /> : null}</div>
      <div hidden={view !== 'knowledge'}>{visited.has('knowledge') ? <ExtractedKnowledge initialEvidence={evidenceTarget} /> : null}</div>
      <div hidden={view !== 'history'}>{visited.has('history') ? <HistoryPage active={view === 'history'} newEnquiry={() => { setAssessmentSession(v => v + 1); window.location.hash = '#assess' }} /> : null}</div>
      <div hidden={view !== 'workspace'}>{visited.has('workspace') ? <WorkspaceStatus /> : null}</div>
    </main>
  </div>
}
