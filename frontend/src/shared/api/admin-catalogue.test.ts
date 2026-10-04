/**
 * Tests for the owner's catalogue routes at the level of the call.
 *
 * The readers check every member of a category and a model, so a body that
 * breaks the contract fails with the name of the field. A key is always
 * encoded into the path, and the publication route is read like every other,
 * because it answers with the model.
 */

import { describe, expect, it } from 'vitest'
import { jsonResponse, mockApi } from '../../test/api-mock'
import {
  CATEGORIES_ROUTE,
  HAMMER,
  MODELS_ROUTE,
  categoryList,
  modelPage,
  modelRoute,
  publicationRoute,
} from '../../test/admin-catalogue-samples'
import { failureOf } from '../../test/session-samples'
import { getAdminModel, listAdminCategories, listAdminModels, setModelPublication } from './admin-catalogue'

describe('the categories', () => {
  it('reads every member, a missing description and a top level parent as null', async () => {
    mockApi({ [CATEGORIES_ROUTE]: () => jsonResponse(categoryList()) })

    await expect(listAdminCategories()).resolves.toEqual(categoryList())
  })

  it('asks for the first page at the largest size the API serves, so every category is on it', async () => {
    const network = mockApi({ [CATEGORIES_ROUTE]: () => jsonResponse(categoryList()) })

    await listAdminCategories()

    expect(Object.fromEntries(network.requests[0].query)).toEqual({ page: '1', pageSize: '100' })
  })

  it('refuses a category that leaves out whether it is switched on, naming the field', async () => {
    const { isActive: _isActive, ...withoutState } = categoryList().items[0]
    mockApi({ [CATEGORIES_ROUTE]: () => jsonResponse({ ...categoryList(), items: [withoutState] }) })

    const failure = await failureOf(listAdminCategories())

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain('isActive')
  })
})

describe('the models', () => {
  it('reads every member of a page', async () => {
    mockApi({ [MODELS_ROUTE]: () => jsonResponse(modelPage()) })

    await expect(listAdminModels({ page: 1, pageSize: 20 })).resolves.toEqual(modelPage())
  })

  it.each([
    ['money with no decimals', { ...HAMMER, lateFeePerDay: '50' }, 'lateFeePerDay'],
    ['a count of units below zero', { ...HAMMER, assetCount: -1 }, 'assetCount'],
    ['a time that is not one', { ...HAMMER, updatedAt: 'yesterday' }, 'updatedAt'],
    ['no answer on whether it is published', { ...HAMMER, isPublished: 'yes' }, 'isPublished'],
  ])('refuses %s, naming the field', async (_what, body, field) => {
    mockApi({ [modelRoute(HAMMER.id)]: () => jsonResponse(body) })

    const failure = await failureOf(getAdminModel(HAMMER.id))

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain(field)
  })

  it('encodes a key into the path', async () => {
    const network = mockApi({})

    await failureOf(getAdminModel('a/b?c'))

    expect(network.requests[0].path).toBe('/api/admin/models/a%2Fb%3Fc')
  })

  it('sends the publication and reads the model it answers with', async () => {
    const hidden = { ...HAMMER, isPublished: false }
    const network = mockApi({ [publicationRoute(HAMMER.id)]: () => jsonResponse(hidden) })

    await expect(setModelPublication(HAMMER.id, false)).resolves.toEqual(hidden)

    expect(network.requests[0].body).toEqual({ published: false })
  })

  it('refuses a publication answer that leaves out whether the model is published, naming the field', async () => {
    const { isPublished: _isPublished, ...withoutState } = HAMMER
    mockApi({ [publicationRoute(HAMMER.id)]: () => jsonResponse(withoutState) })

    const failure = await failureOf(setModelPublication(HAMMER.id, true))

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain('isPublished')
  })
})
