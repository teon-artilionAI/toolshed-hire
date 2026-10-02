/**
 * Tests for today's date in branch time.
 *
 * Every test passes its own instant in, so none depends on when it runs or on
 * the time zone of the machine it runs on.
 */

import { describe, expect, it } from 'vitest'
import { todayInBranchTime } from './today'

describe('todayInBranchTime', () => {
  it('writes the date as YYYY-MM-DD', () => {
    expect(todayInBranchTime(new Date('2026-03-12T10:00:00+02:00'))).toBe('2026-03-12')
  })

  it('is already tomorrow in Cape Town late in the evening UTC', () => {
    // 22:30 UTC on the 12th is 00:30 on the 13th in South Africa.
    expect(todayInBranchTime(new Date('2026-03-12T22:30:00Z'))).toBe('2026-03-13')
  })

  it('is still today in Cape Town just before midnight there', () => {
    expect(todayInBranchTime(new Date('2026-03-12T21:59:59Z'))).toBe('2026-03-12')
  })

  it('does not follow the visitor into another time zone', () => {
    // 20:00 on the 12th in Los Angeles is 05:00 on the 13th in South Africa.
    expect(todayInBranchTime(new Date('2026-03-12T20:00:00-07:00'))).toBe('2026-03-13')
  })

  it('pads a single digit month and day', () => {
    expect(todayInBranchTime(new Date('2026-01-05T09:00:00+02:00'))).toBe('2026-01-05')
  })

  it('rolls over the year end in branch time', () => {
    expect(todayInBranchTime(new Date('2026-12-31T22:00:00Z'))).toBe('2027-01-01')
  })

  it('refuses a date that is not one', () => {
    expect(() => todayInBranchTime(new Date('not a date'))).toThrow(RangeError)
  })

  it('reads the clock when no instant is given', () => {
    expect(todayInBranchTime()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
