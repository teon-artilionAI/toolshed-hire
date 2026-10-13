/**
 * Tests for the words and the small rules of the owner's trading calendar.
 *
 * The closed days grouped by month in the order the server sent them, the
 * form's own checks of a draft, the count of what is left of the reason, and
 * the line above the bookings a closure would strand.
 */

import { describe, expect, it } from 'vitest'
import { ELECTION_DAY, GOOD_FRIDAY, HUMAN_RIGHTS_DAY, STOCKTAKE, impactOf } from '../../test/calendar-samples'
import {
  EVERY_BRANCH_VALUE,
  branchCodeOf,
  draftProblems,
  impactLine,
  lastDayToClose,
  monthsOf,
  reasonCounter,
} from './calendar-words'

const TODAY = '2026-03-12'
const GOOD_DRAFT = { branch: 'CBD', day: '2026-03-27', reason: 'Stocktake' }

describe('monthsOf', () => {
  it('groups the days by month and keeps their order', () => {
    const months = monthsOf([STOCKTAKE, HUMAN_RIGHTS_DAY, GOOD_FRIDAY, ELECTION_DAY])

    expect(months.map((month) => [month.label, month.days.length])).toEqual([
      ['March 2026', 2],
      ['April 2026', 1],
      ['May 2026', 1],
    ])
  })

  it('has no month for no days', () => {
    expect(monthsOf([])).toEqual([])
  })
})

describe('draftProblems', () => {
  it('finds nothing wrong with a full draft', () => {
    expect(draftProblems(GOOD_DRAFT, TODAY)).toEqual({})
  })

  it('names every empty field', () => {
    expect(Object.keys(draftProblems({ branch: '', day: '', reason: '   ' }, TODAY))).toEqual(['branch', 'day', 'reason'])
  })

  it('accepts today and the last day a year on, and refuses the days either side', () => {
    expect(draftProblems({ ...GOOD_DRAFT, day: TODAY }, TODAY).day).toBeUndefined()
    expect(draftProblems({ ...GOOD_DRAFT, day: lastDayToClose(TODAY) }, TODAY).day).toBeUndefined()
    expect(draftProblems({ ...GOOD_DRAFT, day: '2026-03-11' }, TODAY).day).toMatch(/has passed/)
    expect(draftProblems({ ...GOOD_DRAFT, day: '2027-03-14' }, TODAY).day).toMatch(/at most 366 days/)
  })

  it('refuses a day that is not on the calendar', () => {
    expect(draftProblems({ ...GOOD_DRAFT, day: '2026-02-30' }, TODAY).day).toBe('Choose the day to close.')
  })

  it('refuses a reason longer than the server keeps', () => {
    expect(draftProblems({ ...GOOD_DRAFT, reason: 'x'.repeat(121) }, TODAY).reason).toBe('Keep the reason to 120 characters.')
  })
})

describe('the small sayings', () => {
  it('sends null for every branch and the code for one', () => {
    expect(branchCodeOf({ ...GOOD_DRAFT, branch: EVERY_BRANCH_VALUE })).toBeNull()
    expect(branchCodeOf(GOOD_DRAFT)).toBe('CBD')
  })

  it('counts what is left of the reason, and what is over', () => {
    expect(reasonCounter('  Stocktake ')).toBe('111 characters left of 120.')
    expect(reasonCounter('x'.repeat(121))).toBe('1 character too many.')
  })

  it('says how many bookings a closure strands, and when only some are listed', () => {
    expect(impactLine(impactOf([]))).toBe('No booking starts or ends on that day.')
    expect(impactLine(impactOf())).toBe('2 bookings start or end on that day.')
    expect(impactLine(impactOf(undefined, 250))).toBe('250 bookings start or end on that day. The first 2 are listed.')
  })
})
