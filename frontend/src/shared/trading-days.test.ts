import { describe, expect, it } from 'vitest'
import type { Branch, ClosedDay } from './api/contract'
import { closedDayProblem, closedDaysAt, closedEverywhere, nextOpenDay, openPeriod } from './trading-days'

// Saturday 17 October 2026 is a short day, Sunday the 18th is closed, and the
// Cape Town branch closes on Tuesday the 20th for a stocktake.
const SUNDAY: ClosedDay = { day: '2026-10-18', reason: 'is closed on Sundays', kind: 'weekly' }
const STOCKTAKE: ClosedDay = { day: '2026-10-20', reason: 'stocktake', kind: 'closure' }
const CHRISTMAS: ClosedDay = { day: '2026-12-25', reason: 'Christmas Day', kind: 'public_holiday' }

function branch(code: string, closedDays: ClosedDay[]): Branch {
  return { code, name: code, suburb: 'Woodstock', city: 'Cape Town', phone: '021', weeklyHours: [], closedDays }
}

const CBD = branch('CBD', [SUNDAY, STOCKTAKE, CHRISTMAS])
const BLV = branch('BLV', [SUNDAY, CHRISTMAS])

describe('closed days', () => {
  it('are every day one branch is closed', () => {
    expect([...closedDaysAt(CBD).keys()]).toEqual(['2026-10-18', '2026-10-20', '2026-12-25'])
  })

  it('across branches are only the days every branch is closed, so another can serve', () => {
    expect([...closedEverywhere([CBD, BLV]).keys()]).toEqual(['2026-10-18', '2026-12-25'])
  })

  it('are none before the branches arrive', () => {
    expect(closedEverywhere(undefined).size).toBe(0)
    expect(closedDaysAt(undefined).size).toBe(0)
  })
})

describe('the next open day', () => {
  it('is the day itself when it is open', () => {
    expect(nextOpenDay('2026-10-19', closedDaysAt(CBD))).toBe('2026-10-19')
  })

  it('steps over a closed day', () => {
    expect(nextOpenDay('2026-10-18', closedDaysAt(CBD))).toBe('2026-10-19')
  })

  it('gives a period that starts and ends on open days', () => {
    expect(openPeriod('2026-10-18', 1, closedDaysAt(CBD))).toEqual({ startIso: '2026-10-19', endIso: '2026-10-21' })
  })
})

describe('the sentence for a closed day', () => {
  it('names a weekly closing and the next open day', () => {
    expect(closedDayProblem('2026-10-18', closedDaysAt(CBD), true)).toBe(
      'The branch is closed on Sundays, so you cannot collect on 18 Oct 2026. The next open day is 19 Oct 2026.',
    )
  })

  it('names a public holiday when the equipment would come back', () => {
    expect(closedDayProblem('2026-12-25', closedDaysAt(CBD), false)).toBe(
      'The branch is closed for Christmas Day, so you cannot bring equipment back on 25 Dec 2026. ' +
        'The next open day is 26 Dec 2026.',
    )
  })

  it('names the owner\'s reason for a closure day', () => {
    expect(closedDayProblem('2026-10-20', closedDaysAt(CBD), true)).toMatch(/^The branch is closed for stocktake, so/)
  })

  it('is nothing on an open day', () => {
    expect(closedDayProblem('2026-10-19', closedDaysAt(CBD), true)).toBeNull()
  })
})
