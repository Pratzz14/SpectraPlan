// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Claim } from '../src/features/assessment/components/AssessmentResults'
import type { AssessmentRun } from '../src/features/assessment/assessment'

afterEach(cleanup)
const text = 'method: NIR spectroscopy measurement_technique: diffuse reflection probe optical_path_or_depth: 0.5-1 mm'
const run = { assessment:null, retrieval:{evidence:[{evidence:{evidence_id:'T01:row9',content_kind:'method_row',text,raw_values:{method:'NIR spectroscopy',measurement_technique:'diffuse reflection probe',optical_path_or_depth:'0.5-1 mm'}}}]} } as unknown as AssessmentRun

test('full workbook excerpts read as labeled facts and preserve citation inspection', () => {
  const inspect=vi.fn()
  const claim={text:'Source excerpt (general_method): '+text,evidence_ids:['T01:row9']}
  render(<Claim run={run} claim={claim} inspect={inspect} />)
  expect(screen.getByText('Technique')).toBeTruthy()
  expect(screen.getByText('diffuse reflection probe')).toBeTruthy()
  expect(screen.getByText('0.5-1 mm')).toBeTruthy()
  fireEvent.click(screen.getByRole('button'))
  expect(inspect).toHaveBeenCalledWith('T01:row9',claim.text)
})

test('partial source excerpts remain exact prose rather than expanding to the whole row', () => {
  render(<Claim run={run} claim={{text:'Source excerpt (general_method): NIR spectroscopy',evidence_ids:['T01:row9']}} inspect={()=>{}} />)
  expect(screen.getByText('NIR spectroscopy')).toBeTruthy()
  expect(screen.queryByText('Optical path / depth')).toBeNull()
})
