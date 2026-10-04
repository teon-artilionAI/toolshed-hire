/**
 * Tests for what SC-20 keeps in the address. The search, the filters, the page
 * and the model open in the form are read back as they were written, anything
 * the address names that the list cannot use falls back, and the query names
 * only what is applied.
 */

import { describe, expect, it } from 'vitest'
import {
  NEW_MODEL,
  NO_CATALOGUE_FILTERS,
  catalogueIsFiltered,
  modelQueryFor,
  readCatalogueFilters,
  writeCatalogueFilters,
} from './catalogue-address'

const CATEGORY = 'ca700000-0000-4000-8000-000000000002'

describe('the catalogue in the address', () => {
  it('reads back what it wrote', () => {
    const filters = { q: 'hammer', categoryId: CATEGORY, published: false, page: 3, model: NEW_MODEL }

    const written = writeCatalogueFilters(filters)

    expect(written.toString()).toBe(`q=hammer&categoryId=${CATEGORY}&published=false&page=3&model=new`)
    expect(readCatalogueFilters(written)).toEqual(filters)
  })

  it('leaves out every default, so the plain address is the whole list', () => {
    expect(writeCatalogueFilters(NO_CATALOGUE_FILTERS).toString()).toBe('')
    expect(readCatalogueFilters(new URLSearchParams())).toEqual(NO_CATALOGUE_FILTERS)
  })

  it('falls back on a published value and a page it cannot use, and ignores blank filters', () => {
    const read = readCatalogueFilters(new URLSearchParams('q=%20%20&published=maybe&page=-2&categoryId='))

    expect(read).toEqual(NO_CATALOGUE_FILTERS)
  })

  it('counts the search and the two menus as filters, and not the page or the form', () => {
    expect(catalogueIsFiltered({ ...NO_CATALOGUE_FILTERS, page: 4, model: NEW_MODEL })).toBe(false)
    expect(catalogueIsFiltered({ ...NO_CATALOGUE_FILTERS, published: true })).toBe(true)
  })

  it('asks the server for twenty at a time, naming only what is applied', () => {
    expect(modelQueryFor({ ...NO_CATALOGUE_FILTERS, published: false, page: 2 })).toEqual({
      q: undefined,
      categoryId: undefined,
      published: false,
      page: 2,
      pageSize: 20,
    })
  })
})
