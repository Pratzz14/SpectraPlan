import { useEffect, useState } from 'react'

type View = 'assess' | 'search' | 'knowledge' | 'history' | 'workspace'
function currentView(): View {
  const route = window.location.hash.split('?')[0]
  return route === '#history' ? 'history' : route === '#search' ? 'search' : route === '#knowledge' ? 'knowledge' : ['#workspace', '#status'].includes(route) ? 'workspace' : 'assess'
}

export function useNavigation() {
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
  return { view, visited, evidenceTarget, runTarget, assessmentSession, setAssessmentSession }
}
