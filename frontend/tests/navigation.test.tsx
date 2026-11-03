// @vitest-environment jsdom
import { afterEach, expect, test } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import { useNavigation } from '../src/app/useNavigation'

afterEach(cleanup)
test('navigation preserves visited pages and deep-link targets', () => {
  window.location.hash = '#assess?run=saved-run'
  const { result } = renderHook(() => useNavigation())
  expect(result.current.runTarget).toBe('saved-run')
  act(() => {
    window.location.hash = '#knowledge?evidence=source-id'
    window.dispatchEvent(new Event('hashchange'))
  })
  expect(result.current.view).toBe('knowledge')
  expect(result.current.evidenceTarget).toBe('source-id')
  expect(result.current.visited.has('assess')).toBe(true)
  expect(result.current.visited.has('knowledge')).toBe(true)
  expect(result.current.runTarget).toBe('')
})
