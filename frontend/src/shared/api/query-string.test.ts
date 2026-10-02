/**
 * Tests for the query string builder.
 *
 * I check the string that goes on the wire, because that is what the API reads.
 */

import { describe, expect, it } from 'vitest'
import type { AvailabilityQuery } from './contract'
import { buildQueryString } from './query-string'

describe('buildQueryString', () => {
  it('writes each parameter and encodes what needs encoding', () => {
    expect(buildQueryString({ q: 'cut-off saw & blade', page: 2 })).toBe(
      '?q=cut-off+saw+%26+blade&page=2',
    )
  })

  it('leaves out anything undefined, null or empty', () => {
    expect(buildQueryString({ from: '2026-03-12', q: '', category: undefined, branch: null })).toBe(
      '?from=2026-03-12',
    )
  })

  it('keeps zero and false, which are values and not gaps', () => {
    expect(buildQueryString({ offset: 0, active: false })).toBe('?offset=0&active=false')
  })

  it('is empty when there is nothing to send', () => {
    expect(buildQueryString({})).toBe('')
    expect(buildQueryString()).toBe('')
  })

  it('takes a query typed by an interface from the contract', () => {
    const query: AvailabilityQuery = { from: '2026-03-12', to: '2026-03-16', sort: 'dailyRateAsc', page: 2 }

    expect(buildQueryString(query)).toBe('?from=2026-03-12&to=2026-03-16&sort=dailyRateAsc&page=2')
  })
})
