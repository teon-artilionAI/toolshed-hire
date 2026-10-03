/**
 * Tests for the calendar arithmetic of the diary.
 *
 * The functions are pure, so each test hands one a date and reads what comes
 * back. The awkward days are the ones that matter. The end of a month, the
 * end of a year, a Sunday, and dates in the address that are not days at all.
 */

import { describe, expect, it } from 'vitest'
import { addDays, dayName, readIsoDate, startOfWeek } from './diary-dates'

describe('readIsoDate', () => {
  it('keeps a real day written YYYY-MM-DD', () => {
    expect(readIsoDate('2026-03-12')).toBe('2026-03-12')
    expect(readIsoDate('2028-02-29')).toBe('2028-02-29')
  })

  it.each([null, '', 'today', '2026-3-12', '2026-02-30', '2026-13-01', '2027-02-29', '2026-03-12T00:00'])(
    'refuses %s, which is not a day on the calendar',
    (value) => {
      expect(readIsoDate(value)).toBeNull()
    },
  )
})

describe('addDays', () => {
  it('goes forward and back across the end of a month and a year', () => {
    expect(addDays('2026-03-12', 1)).toBe('2026-03-13')
    expect(addDays('2026-03-31', 1)).toBe('2026-04-01')
    expect(addDays('2026-12-28', 7)).toBe('2027-01-04')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
  })
})

describe('startOfWeek', () => {
  it.each([
    ['2026-03-12', '2026-03-09'],
    ['2026-03-09', '2026-03-09'],
    ['2026-03-15', '2026-03-09'],
    ['2027-01-01', '2026-12-28'],
  ])('puts %s in the week that starts on Monday %s', (date, monday) => {
    expect(startOfWeek(date)).toBe(monday)
  })
})

describe('dayName', () => {
  it('writes the day out in full, without a comma', () => {
    expect(dayName('2026-03-12')).toBe('Thursday 12 March 2026')
    expect(dayName('2026-10-03')).toBe('Saturday 3 October 2026')
  })
})
