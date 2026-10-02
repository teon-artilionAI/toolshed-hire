/**
 * Tests for today's date in branch time, and for writing an instant the API
 * sent as a time of day at the branches.
 *
 * Every test passes its own instant in, so none depends on when it runs or on
 * the time zone of the machine it runs on.
 */

import { describe, expect, it } from 'vitest'
import { branchClockTime, branchDateTime, todayInBranchTime } from './today'

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

describe('an instant written in branch time', () => {
  it('writes the time of day as HH:MM on a 24 hour clock', () => {
    expect(branchClockTime('2026-10-02T15:30:00+02:00')).toBe('15:30')
    expect(branchClockTime('2026-10-02T00:05:00+02:00')).toBe('00:05')
  })

  it('does not follow the offset the instant was written with', () => {
    // 13:30 UTC is 15:30 at the branches, whatever zone wrote it down.
    expect(branchClockTime('2026-10-02T13:30:00Z')).toBe('15:30')
    expect(branchClockTime('2026-10-02T06:30:00-07:00')).toBe('15:30')
  })

  it('writes the day and the time of day together', () => {
    // Whether a single digit day is padded is the locale data's choice.
    expect(branchDateTime('2026-10-02T15:30:00+02:00')).toMatch(/^0?2 Oct 2026 at 15:30$/)
  })

  it('uses the day at the branches when that is already tomorrow', () => {
    expect(branchDateTime('2026-10-02T22:30:00Z')).toMatch(/^0?3 Oct 2026 at 00:30$/)
  })

  it('refuses a string that is not an instant', () => {
    expect(() => branchClockTime('half past three')).toThrow(RangeError)
    expect(() => branchDateTime('')).toThrow(RangeError)
  })
})
