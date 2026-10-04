/**
 * Tests for what SC-21 keeps in the address. The search, the filters, the
 * page and what is open are read back as they were written, anything the
 * address names that the register cannot use falls back, and the query names
 * only what is applied.
 */

import { describe, expect, it } from 'vitest'
import {
  NO_ASSET_FILTERS,
  assetQueryFor,
  assetsAreFiltered,
  readAssetFilters,
  unitHref,
  writeAssetFilters,
} from './asset-address'

const MODEL = 'a0de1000-0000-4000-8000-000000000001'

describe('the register in the address', () => {
  it('reads back what it wrote', () => {
    const filters = { ...NO_ASSET_FILTERS, q: 'gbh', branchCode: 'BLV', status: 'QUARANTINED' as const, modelId: MODEL, page: 3, asset: 'TSH-DR-0042' }

    const written = writeAssetFilters(filters)

    expect(written.toString()).toBe(`q=gbh&branchCode=BLV&status=QUARANTINED&modelId=${MODEL}&page=3&asset=TSH-DR-0042`)
    expect(readAssetFilters(written)).toEqual(filters)
  })

  it('leaves out every default, so the plain address is the whole register', () => {
    expect(writeAssetFilters(NO_ASSET_FILTERS).toString()).toBe('')
    expect(readAssetFilters(new URLSearchParams())).toEqual(NO_ASSET_FILTERS)
  })

  it('falls back on a status and a page it cannot use, and ignores blank filters', () => {
    const read = readAssetFilters(new URLSearchParams('q=%20%20&status=SOLD&page=-2&branchCode='))

    expect(read).toEqual(NO_ASSET_FILTERS)
  })

  it('opens the registration form, and never with a unit open beside it', () => {
    expect(readAssetFilters(new URLSearchParams('add=unit')).adding).toBe(true)
    expect(readAssetFilters(new URLSearchParams('add=unit&asset=TSH-DR-0042')).adding).toBe(false)
    expect(writeAssetFilters({ ...NO_ASSET_FILTERS, adding: true, asset: 'TSH-DR-0042' }).toString()).toBe('asset=TSH-DR-0042')
  })

  it('counts the search and the three menus as filters, and not the page or what is open', () => {
    expect(assetsAreFiltered({ ...NO_ASSET_FILTERS, page: 4, asset: 'TSH-DR-0042', adding: true })).toBe(false)
    expect(assetsAreFiltered({ ...NO_ASSET_FILTERS, modelId: MODEL })).toBe(true)
  })

  it('asks the server for twenty at a time, naming only what is applied', () => {
    expect(assetQueryFor({ ...NO_ASSET_FILTERS, status: 'RETIRED', page: 2 })).toEqual({
      q: undefined,
      branchCode: undefined,
      status: 'RETIRED',
      modelId: undefined,
      page: 2,
      pageSize: 20,
    })
  })

  it('opens a unit and keeps the filters and the page', () => {
    expect(unitHref({ ...NO_ASSET_FILTERS, status: 'AVAILABLE', page: 2, adding: true }, 'TSH-DR-0042')).toBe(
      '/admin/assets?status=AVAILABLE&page=2&asset=TSH-DR-0042',
    )
  })
})
