/**
 * Tests for the money, date and day counting helpers.
 *
 * I check what a person reading the screen would see, never how the helper
 * gets there. The dates I use all have two digit days, so the tests do not
 * depend on whether the locale data pads a single digit day with a zero.
 */

import { describe, expect, it } from 'vitest'
import {
  daysBetween,
  formatDate,
  formatDateShort,
  formatDateTime,
  humanise,
  isNegativeMoney,
  isNoMoney,
  money,
  percent,
  unsignedMoney,
} from './format'

/** The no-break spaces a locale formatter likes to use between digit groups. */
const NO_BREAK_SPACES = /[  ]/

describe('money', () => {
  // I accept a comma or a point as the decimal mark. That choice belongs to
  // the locale data shipped with the runtime, not to this helper.
  it('writes rand with an R and two decimals', () => {
    expect(money(450)).toMatch(/^R 450[,.]00$/)
  })

  it('keeps two decimals when the amount has cents', () => {
    expect(money(1234.5)).toMatch(/[,.]50$/)
    expect(money(0.5)).toMatch(/^R 0[,.]50$/)
  })

  it('rounds to the nearest cent', () => {
    expect(money(19.999)).toMatch(/^R 20[,.]00$/)
  })

  it('shows zero as a real amount, not as an empty string', () => {
    expect(money(0)).toMatch(/^R 0[,.]00$/)
  })

  it('keeps every digit of a large amount', () => {
    const digitsOnly = money(1234567.89).replace(/\D/g, '')
    expect(digitsOnly).toBe('123456789')
  })

  it('uses plain spaces, so figures can be matched as ordinary text', () => {
    expect(money(1234567.89)).not.toMatch(NO_BREAK_SPACES)
  })

  it('never shows the ISO currency code', () => {
    expect(money(450)).not.toContain('ZAR')
  })
})

describe('money, given a string as the API sends it', () => {
  it('writes the figure the same way it writes a number', () => {
    expect(money('280.00')).toMatch(/^R 280[,.]00$/)
    expect(money('280.00')).toBe(money(280))
    expect(money('1234567.89')).toBe(money(1234567.89))
  })

  it('shows the cents exactly as they arrived', () => {
    expect(money('0.10')).toMatch(/^R 0[,.]10$/)
    expect(money('19.99')).toMatch(/^R 19[,.]99$/)
    expect(money('0.00')).toMatch(/^R 0[,.]00$/)
  })

  it('keeps every digit of an amount too large for a float to hold', () => {
    // As a float this is 9007199254740993.57, which rounds to a neighbour and
    // would show a different figure from the one that was sent.
    const digitsOnly = money('9007199254740993.57').replace(/\D/g, '')

    expect(digitsOnly).toBe('900719925474099357')
  })

  it('pads a figure written with fewer than two decimals', () => {
    expect(money('280')).toBe(money('280.00'))
    expect(money('280.5')).toBe(money('280.50'))
  })

  it('writes a negative amount with its sign', () => {
    expect(money('-45.50')).toBe(money(-45.5))
  })

  it('uses plain spaces and never the ISO currency code', () => {
    expect(money('1234567.89')).not.toMatch(NO_BREAK_SPACES)
    expect(money('1234567.89')).not.toContain('ZAR')
  })

  it.each(['', 'abc', '12.345', '1,200.00', 'R 280.00', '1e3'])(
    'refuses "%s" and does not guess at a figure',
    (amount) => {
      expect(() => money(amount)).toThrow(RangeError)
    },
  )
})

describe('isNoMoney', () => {
  it.each(['0.00', '0', '-0.00', '000.0'])('says "%s" is nothing', (amount) => {
    expect(isNoMoney(amount)).toBe(true)
  })

  it.each(['0.01', '1.00', '-12.50'])('says "%s" is something', (amount) => {
    expect(isNoMoney(amount)).toBe(false)
  })

  it('refuses an amount that is not money', () => {
    expect(() => isNoMoney('lots')).toThrow(RangeError)
  })
})

describe('isNegativeMoney and unsignedMoney', () => {
  it('says a deposit given back runs the other way, and writes it with no minus', () => {
    expect(isNegativeMoney('-960.00')).toBe(true)
    expect(unsignedMoney('-960.00')).toBe(money('960.00'))
    expect(unsignedMoney('-960.00')).not.toContain('-')
  })

  it.each(['0.00', '-0.00', '240.00'])('says "%s" is not negative and writes it as it is', (amount) => {
    expect(isNegativeMoney(amount)).toBe(false)
    expect(unsignedMoney(amount)).toBe(money(amount.replace('-', '')))
  })

  it('refuses an amount that is not money', () => {
    expect(() => isNegativeMoney('lots')).toThrow(RangeError)
    expect(() => unsignedMoney('--5.00')).toThrow(RangeError)
  })
})

describe('percent', () => {
  it('drops decimals that are all zeros', () => {
    expect(percent('15.00')).toBe('15%')
    expect(percent('0.00')).toBe('0%')
  })

  it('keeps decimals that say something', () => {
    expect(percent('12.50')).toMatch(/^12[,.]5%$/)
    expect(percent('7.25')).toMatch(/^7[,.]25%$/)
  })

  it.each(['', 'fifteen', '15%', '-5.00', '1.234'])(
    'refuses "%s" and does not guess at a rate',
    (rate) => {
      expect(() => percent(rate)).toThrow(RangeError)
    },
  )
})

describe('formatDate', () => {
  it('writes the day, the short month and the year', () => {
    expect(formatDate('2026-03-12')).toBe('12 Mar 2026')
  })

  it('handles the last day of the year', () => {
    expect(formatDate('2026-12-31')).toBe('31 Dec 2026')
  })
})

describe('formatDateShort', () => {
  it('leaves the year out', () => {
    expect(formatDateShort('2026-03-12')).toBe('12 Mar')
  })
})

describe('formatDateTime', () => {
  it('shows the short date and the time on a 24 hour clock', () => {
    expect(formatDateTime('2026-03-12T14:05:00')).toBe('12 Mar 14:05')
  })

  it('shows a UTC instant in branch time, two hours ahead', () => {
    expect(formatDateTime('2026-03-12T07:30:00Z')).toBe('12 Mar 09:30')
  })
})

describe('daysBetween', () => {
  it('treats the period as half open, so the return day is not charged', () => {
    // The 6th, 7th, 8th and 9th. The unit is free again on the 10th.
    expect(daysBetween('2026-03-06', '2026-03-10')).toBe(4)
  })

  it('counts an overnight hire as one day, not two', () => {
    expect(daysBetween('2026-03-06', '2026-03-07')).toBe(1)
  })

  it('counts nothing when collection and return are the same day', () => {
    expect(daysBetween('2026-03-06', '2026-03-06')).toBe(0)
  })

  it('never goes negative when the dates are the wrong way round', () => {
    expect(daysBetween('2026-03-10', '2026-03-06')).toBe(0)
  })

  it('counts across a month end', () => {
    // 27 and 28 February, then 1 March. 2026 is not a leap year.
    expect(daysBetween('2026-02-27', '2026-03-02')).toBe(3)
  })

  it('lets back to back hires share a boundary day without overlapping', () => {
    const first = daysBetween('2026-03-06', '2026-03-10')
    const second = daysBetween('2026-03-10', '2026-03-13')
    expect(first + second).toBe(daysBetween('2026-03-06', '2026-03-13'))
  })
})

describe('humanise', () => {
  it('turns an enum value into words a person can read', () => {
    expect(humanise('ON_HIRE')).toBe('On Hire')
    expect(humanise('PARTIALLY_RETURNED')).toBe('Partially Returned')
  })

  it('handles a single word', () => {
    expect(humanise('AVAILABLE')).toBe('Available')
  })
})
