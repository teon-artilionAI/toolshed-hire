/**
 * Tests for the small helpers under the catalogue screens. The hire period,
 * the search as the address holds it, and the links between the screens.
 *
 * Every test that needs today passes it in, so none depends on the clock.
 */

import { describe, expect, it } from 'vitest'
import { modelDetailHref, searchHref } from './catalogue-links'
import {
  defaultPeriod,
  describePeriod,
  hireDays,
  isIsoDate,
  validatePeriod,
} from './hire-period'
import { availabilityQueryFor, readSearchFilters, writeSearchFilters } from './search-filters'

const TODAY = '2026-03-12'

describe('isIsoDate', () => {
  it('accepts a real date written as YYYY-MM-DD', () => {
    expect(isIsoDate('2026-03-12')).toBe(true)
    expect(isIsoDate('2028-02-29')).toBe(true)
  })

  it.each(['', 'banana', '12/03/2026', '2026-3-12', '2026-02-30', '2026-13-01', '2026-03-12T10:00'])(
    'refuses "%s"',
    (value) => {
      expect(isIsoDate(value)).toBe(false)
    },
  )
})

describe('the hire period', () => {
  it('opens on today for four days', () => {
    expect(defaultPeriod(TODAY)).toEqual({ startIso: '2026-03-12', endIso: '2026-03-16' })
  })

  it('counts the days half open, and never fewer than one', () => {
    expect(hireDays('2026-03-06', '2026-03-10')).toBe(4)
    expect(hireDays('2026-03-06', '2026-03-06')).toBe(1)
  })

  it('is described in words, or not at all when a date is not real', () => {
    expect(describePeriod('2026-03-12', '2026-03-16')).toBe('12 Mar 2026 to 16 Mar 2026')
    expect(describePeriod('banana', '2026-03-16')).toBeNull()
    expect(describePeriod('2026-03-12', '')).toBeNull()
  })

  it('is usable when it starts today or later and ends after it starts', () => {
    expect(validatePeriod('2026-03-12', '2026-03-13', TODAY)).toBeNull()
  })

  it('is measured against the today it is given', () => {
    expect(validatePeriod('2026-03-12', '2026-03-13', '2026-03-13')).toMatch(/cannot be in the past/)
  })

  it('says what is wrong in the words a customer would use', () => {
    expect(validatePeriod('', '2026-03-13', TODAY)).toBe('Choose a collection date.')
    expect(validatePeriod('2026-03-12', 'banana', TODAY)).toBe('Choose a return date.')
    expect(validatePeriod('2026-03-14', '2026-03-14', TODAY)).toMatch(/must be after/)
    expect(validatePeriod('2026-03-12', '2026-05-12', TODAY)).toMatch(/up to 28 days/)
  })
})

describe('the search in the address', () => {
  it('opens a bare address on the default dates and no filters', () => {
    expect(readSearchFilters(new URLSearchParams(''), TODAY)).toEqual({
      from: '2026-03-12',
      to: '2026-03-16',
      q: '',
      category: '',
      branch: '',
      sort: 'name',
      page: 1,
    })
  })

  it('reads back exactly what it wrote', () => {
    const filters = {
      from: '2026-03-20',
      to: '2026-03-23',
      q: 'cut-off saw',
      category: 'cutting-grinding',
      branch: 'SMW',
      sort: 'dailyRateDesc' as const,
      page: 3,
    }

    expect(readSearchFilters(writeSearchFilters(filters), TODAY)).toEqual(filters)
  })

  it('leaves defaults out of the address, so a shared link stays short', () => {
    const filters = readSearchFilters(new URLSearchParams('from=2026-03-20&to=2026-03-23'), TODAY)

    expect(writeSearchFilters(filters).toString()).toBe('from=2026-03-20&to=2026-03-23')
  })

  it.each([
    ['sort=cheapest', 'name', 1],
    ['page=0', 'name', 1],
    ['page=-4', 'name', 1],
    ['page=two', 'name', 1],
    ['sort=dailyRateAsc&page=7', 'dailyRateAsc', 7],
  ])('falls back to a sort and a page it can offer for "%s"', (search, sort, page) => {
    const filters = readSearchFilters(new URLSearchParams(search), TODAY)

    expect(filters.sort).toBe(sort)
    expect(filters.page).toBe(page)
  })

  it('keeps a cleared date cleared, and then has nothing to ask the API', () => {
    const filters = readSearchFilters(new URLSearchParams('from=&to=2026-03-16'), TODAY)

    expect(filters.from).toBe('')
    expect(writeSearchFilters(filters).toString()).toBe('from=&to=2026-03-16')
    expect(availabilityQueryFor(filters)).toBeNull()
  })

  it('asks the API for the filters that are set, and a text search of two letters or more', () => {
    const filters = readSearchFilters(
      new URLSearchParams('from=2026-03-20&to=2026-03-23&q=ra&branch=BLV'),
      TODAY,
    )

    expect(availabilityQueryFor(filters)).toEqual({
      from: '2026-03-20',
      to: '2026-03-23',
      q: 'ra',
      category: undefined,
      branch: 'BLV',
      sort: 'name',
      page: 1,
      pageSize: 24,
    })
    expect(availabilityQueryFor({ ...filters, q: 'r' })?.q).toBeUndefined()
  })
})

describe('the links between the catalogue screens', () => {
  it('address a model by its slug and carry the dates', () => {
    expect(modelDetailHref('cp-100-plate-compactor', { from: '2026-03-12', to: '2026-03-16' })).toBe(
      '/model/cp-100-plate-compactor?from=2026-03-12&to=2026-03-16',
    )
  })

  it('carry the branch when one is chosen', () => {
    expect(
      modelDetailHref('cp-100-plate-compactor', { from: '2026-03-12', to: '2026-03-16' }, 'BLV'),
    ).toBe('/model/cp-100-plate-compactor?from=2026-03-12&to=2026-03-16&branch=BLV')
  })

  it('encode a slug that is not address safe', () => {
    expect(modelDetailHref('a/b c', { from: '2026-03-12', to: '2026-03-16' })).toBe(
      '/model/a%2Fb%20c?from=2026-03-12&to=2026-03-16',
    )
  })

  it('open the search on a category', () => {
    expect(searchHref({ from: '2026-03-12', to: '2026-03-16' }, 'compaction')).toBe(
      '/search?from=2026-03-12&to=2026-03-16&category=compaction',
    )
  })
})
