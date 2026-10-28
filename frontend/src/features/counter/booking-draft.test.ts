import { describe, expect, it } from 'vitest'
import type { ClosedDay } from '../../shared/api/contract'
import { draftProblems, emptyDraft } from './booking-draft'

// Thursday 12 March 2026. Saturday the 14th is a short day and Sunday the 15th
// the branch is closed.
const TODAY = '2026-03-12'
const SUNDAY: ClosedDay = { day: '2026-03-15', reason: 'is closed on Sundays', kind: 'weekly' }
const CLOSED = new Map([[SUNDAY.day, SUNDAY]])
const A_LINE = { modelSlug: 'cp-100', modelName: 'CP 100', quantity: 1 }

describe('the draft a booking opens with', () => {
  it('goes out today and comes back tomorrow when both are open', () => {
    expect(emptyDraft(TODAY, CLOSED)).toEqual({ from: '2026-03-12', to: '2026-03-13', lines: [] })
  })

  it('moves to the next open day when today is closed', () => {
    expect(emptyDraft('2026-03-15', CLOSED)).toEqual({ from: '2026-03-16', to: '2026-03-17', lines: [] })
  })

  it('moves the return past a closed day', () => {
    expect(emptyDraft('2026-03-14', CLOSED)).toEqual({ from: '2026-03-14', to: '2026-03-16', lines: [] })
  })
})

describe('the problems of a draft', () => {
  it('names a closed day the equipment would go out or come back on', () => {
    expect(draftProblems({ from: '2026-03-15', to: '2026-03-16', lines: [A_LINE] }, TODAY, CLOSED).from).toMatch(
      /^The branch is closed on Sundays, so you cannot collect on 15 Mar 2026\./,
    )
    expect(draftProblems({ from: '2026-03-13', to: '2026-03-15', lines: [A_LINE] }, TODAY, CLOSED).to).toMatch(
      /cannot bring equipment back on 15 Mar 2026/,
    )
  })

  it('has none for open days', () => {
    expect(draftProblems({ from: '2026-03-13', to: '2026-03-16', lines: [A_LINE] }, TODAY, CLOSED)).toEqual({})
  })
})
