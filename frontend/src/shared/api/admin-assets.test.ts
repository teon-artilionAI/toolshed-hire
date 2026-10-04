/**
 * Tests for the asset register routes at the level of the call.
 *
 * The readers check every member of a unit and of its history, so a body that
 * breaks the contract fails with the name of the field. A tag is always
 * encoded into the path, and every write is read like the unit's own read,
 * because each answers with the unit and its history.
 */

import { describe, expect, it } from 'vitest'
import { createdResponse, jsonResponse, mockApi } from '../../test/api-mock'
import {
  ASSETS_ROUTE,
  INTAKE_UNIT,
  REGISTER_ROUTE,
  SHELF_UNIT,
  assetPage,
  assetRoute,
  detailOf,
  moveRoute,
} from '../../test/admin-asset-samples'
import { failureOf } from '../../test/session-samples'
import { changeAsset, getAdminAsset, listAdminAssets, moveAsset, registerAsset } from './admin-assets'

describe('the register', () => {
  it('reads every member of a page, nulls and an empty list of moves included', async () => {
    mockApi({ [ASSETS_ROUTE]: () => jsonResponse(assetPage()) })

    await expect(listAdminAssets({ page: 1, pageSize: 20 })).resolves.toEqual(assetPage())
  })

  it('sends only the filters that are given', async () => {
    const network = mockApi({ [ASSETS_ROUTE]: () => jsonResponse(assetPage()) })

    await listAdminAssets({ q: 'gbh', status: 'RETIRED', page: 2, pageSize: 20 })

    expect(network.requests[0].query.toString()).toBe('q=gbh&status=RETIRED&page=2&pageSize=20')
  })

  it.each([
    ['a move to a status the register does not know', { ...SHELF_UNIT, allowedTransitions: ['SOLD'] }, 'allowedTransitions'],
    ['a cost with no decimals', { ...SHELF_UNIT, acquisitionCost: '3980' }, 'acquisitionCost'],
    ['a grade the counter does not use', { ...SHELF_UNIT, conditionGrade: 'D' }, 'conditionGrade'],
    ['a meter reading below zero', { ...SHELF_UNIT, hourMeterReading: -1 }, 'hourMeterReading'],
    ['no day of retirement at all', { ...SHELF_UNIT, retiredOn: undefined }, 'retiredOn'],
  ])('refuses %s, naming the field', async (_what, body, field) => {
    mockApi({ [assetRoute(SHELF_UNIT.assetTag)]: () => jsonResponse({ ...body, history: [] }) })

    const failure = await failureOf(getAdminAsset(SHELF_UNIT.assetTag))

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain(field)
  })

  it('refuses a history entry of a kind it does not know, naming the field', async () => {
    const history = [{ at: '2026-03-11T09:15:00+02:00', kind: 'SALE', summary: 'Sold.', reference: null }]
    mockApi({ [assetRoute(SHELF_UNIT.assetTag)]: () => jsonResponse({ ...SHELF_UNIT, history }) })

    const failure = await failureOf(getAdminAsset(SHELF_UNIT.assetTag))

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain('kind')
  })

  it('encodes a tag into the path', async () => {
    const network = mockApi({})

    await failureOf(getAdminAsset('a/b?c'))

    expect(network.requests[0].path).toBe('/api/admin/assets/a%2Fb%3Fc')
  })
})

describe('the writes', () => {
  const answer = detailOf(INTAKE_UNIT, [])

  it('registers a unit and reads the 201 with the unit and its history', async () => {
    mockApi({ [REGISTER_ROUTE]: () => createdResponse(answer) })
    const body = {
      assetTag: INTAKE_UNIT.assetTag,
      modelId: INTAKE_UNIT.modelId,
      branchCode: 'CBD',
      serialNumber: null,
      conditionGrade: 'A' as const,
      acquiredOn: '2026-03-10',
      acquisitionCost: '3980.00',
      hourMeterReading: null,
      notes: null,
    }

    await expect(registerAsset(body)).resolves.toEqual(answer)
  })

  it('sends a change and a move to the unit by its tag', async () => {
    const network = mockApi({
      [assetRoute(INTAKE_UNIT.assetTag, 'PATCH')]: () => jsonResponse(answer),
      [moveRoute(INTAKE_UNIT.assetTag)]: () => jsonResponse(answer),
    })

    await changeAsset(INTAKE_UNIT.assetTag, { notes: null })
    await moveAsset(INTAKE_UNIT.assetTag, { to: 'QUARANTINED', reason: 'Smells of burning.' })

    expect(network.requests.map((request) => request.body)).toEqual([
      { notes: null },
      { to: 'QUARANTINED', reason: 'Smells of burning.' },
    ])
  })
})
