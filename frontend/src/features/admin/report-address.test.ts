/**
 * Tests for what the SC-22 report keeps in the address.
 *
 * The default period is the last full calendar month at the branches, the
 * address names a period as a whole or not at all, and writing it out leaves
 * out only what is not applied.
 */

import { describe, expect, it } from 'vitest'
import {
  REPORT_PAGE_SIZE,
  addressSays,
  csvQueryFor,
  lastFullMonth,
  readReportFilters,
  reportQueryFor,
  writeReportFilters,
} from './report-address'

const TODAY = '2026-10-04'

describe('the last full month', () => {
  it('is the month before the one today falls in, up to and not including its first day', () => {
    expect(lastFullMonth(TODAY)).toEqual({ from: '2026-09-01', to: '2026-10-01' })
  })

  it('is December of the year before in January', () => {
    expect(lastFullMonth('2027-01-15')).toEqual({ from: '2026-12-01', to: '2027-01-01' })
  })

  it('is the month before on the first day of a month', () => {
    expect(lastFullMonth('2026-03-01')).toEqual({ from: '2026-02-01', to: '2026-03-01' })
  })
})

describe('reading the address', () => {
  it('starts at the last full month, by model, every branch and category, first page', () => {
    expect(readReportFilters(new URLSearchParams(), TODAY)).toEqual({
      from: '2026-09-01',
      to: '2026-10-01',
      groupBy: 'model',
      branchCode: null,
      categorySlug: null,
      page: 1,
    })
  })

  it('takes what a link names', () => {
    const params = new URLSearchParams('from=2026-01-01&to=2026-04-01&groupBy=asset&branchCode=BLV&categorySlug=compaction&page=3')

    expect(readReportFilters(params, TODAY)).toEqual({
      from: '2026-01-01',
      to: '2026-04-01',
      groupBy: 'asset',
      branchCode: 'BLV',
      categorySlug: 'compaction',
      page: 3,
    })
  })

  it('keeps a period the server will refuse, so the server can say why', () => {
    const params = new URLSearchParams('from=2026-05-01&to=2026-04-01')

    expect(readReportFilters(params, TODAY)).toMatchObject({ from: '2026-05-01', to: '2026-04-01' })
  })

  it.each([
    ['a day that is not on the calendar', 'from=2026-09-31&to=2026-10-01'],
    ['a period with one end missing', 'from=2026-08-01'],
    ['a period that is not dates', 'from=last-month&to=now'],
  ])('falls back to the last full month as a whole for %s', (_what, query) => {
    expect(readReportFilters(new URLSearchParams(query), TODAY)).toMatchObject({ from: '2026-09-01', to: '2026-10-01' })
  })

  it('falls back to the model and the first page for values it cannot read', () => {
    const params = new URLSearchParams('groupBy=profit&page=-2&branchCode=%20')

    expect(readReportFilters(params, TODAY)).toMatchObject({ groupBy: 'model', page: 1, branchCode: null })
  })
})

describe('writing the address', () => {
  it('always names the period and the grouping, and leaves out a filter not applied and the first page', () => {
    const filters = readReportFilters(new URLSearchParams(), TODAY)

    expect(writeReportFilters(filters).toString()).toBe('from=2026-09-01&to=2026-10-01&groupBy=model')
    expect(writeReportFilters({ ...filters, branchCode: 'CBD', page: 2 }).toString()).toBe(
      'from=2026-09-01&to=2026-10-01&groupBy=model&branchCode=CBD&page=2',
    )
  })

  it('says whether an address already names exactly what is shown', () => {
    const empty = new URLSearchParams()
    const filters = readReportFilters(empty, TODAY)

    expect(addressSays(empty, filters)).toBe(false)
    expect(addressSays(writeReportFilters(filters), filters)).toBe(true)
  })
})

describe('the queries', () => {
  it('ask for one page of the report, and every row of the CSV', () => {
    const filters = { ...readReportFilters(new URLSearchParams(), TODAY), branchCode: 'SMW', page: 4 }

    expect(reportQueryFor(filters)).toEqual({
      from: '2026-09-01',
      to: '2026-10-01',
      groupBy: 'model',
      branchCode: 'SMW',
      categorySlug: undefined,
      page: 4,
      pageSize: REPORT_PAGE_SIZE,
    })
    expect(csvQueryFor(filters)).toEqual({
      from: '2026-09-01',
      to: '2026-10-01',
      groupBy: 'model',
      branchCode: 'SMW',
      categorySlug: undefined,
    })
  })
})
