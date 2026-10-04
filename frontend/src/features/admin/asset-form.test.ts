/**
 * Tests for the two forms of SC-21 as bodies. A registration sends every
 * field, trimmed, with money written the way the API takes it and empty
 * optional fields as null. A change sends only what differs from what the
 * server holds. The forms only hold back what cannot be written as a body.
 * The moves are said in words, and the booking a refusal names is cut out of
 * its sentence as a link.
 */

import { describe, expect, it } from 'vitest'
import { SHELF_UNIT } from '../../test/admin-asset-samples'
import {
  EMPTY_NEW_ASSET_DRAFT,
  assetChangesFrom,
  draftOfAsset,
  newAssetRequestFrom,
  plainCostMessage,
} from './asset-form'
import { moveWords, sentenceWithBookings } from './asset-words'

const MODEL = 'a0de1000-0000-4000-8000-000000000001'

describe('the body of a new unit', () => {
  it('sends every field, trimmed, with the cost in two decimals and empty optional fields as null', () => {
    const checked = newAssetRequestFrom({
      ...EMPTY_NEW_ASSET_DRAFT,
      assetTag: ' TSH-DR-0047 ',
      modelId: MODEL,
      branchCode: 'CBD',
      acquiredOn: '2026-03-10',
      acquisitionCost: '3980,5',
      serialNumber: '  ',
    })

    expect(checked.body).toEqual({
      assetTag: 'TSH-DR-0047',
      modelId: MODEL,
      branchCode: 'CBD',
      serialNumber: null,
      conditionGrade: 'A',
      acquiredOn: '2026-03-10',
      acquisitionCost: '3980.50',
      hourMeterReading: null,
      notes: null,
    })
  })

  it('sends a cost that is not an amount as it was typed, so the server says what is wrong', () => {
    const checked = newAssetRequestFrom({ ...EMPTY_NEW_ASSET_DRAFT, modelId: MODEL, branchCode: 'CBD', acquiredOn: '2026-03-10', acquisitionCost: 'free' })

    expect(checked.body?.acquisitionCost).toBe('free')
  })

  it('holds back only what cannot be written as a body', () => {
    const checked = newAssetRequestFrom({ ...EMPTY_NEW_ASSET_DRAFT, hourMeterReading: '12.5' })

    expect(Object.keys(checked.errors ?? {}).sort()).toEqual(['acquiredOn', 'branchCode', 'hourMeterReading', 'modelId'])
  })

  it('puts a refused cost in plain words, and leaves one the server could read alone', () => {
    const sent = { ...EMPTY_NEW_ASSET_DRAFT, conditionGrade: 'A' as const, hourMeterReading: null, serialNumber: null, notes: null }
    expect(plainCostMessage({ acquisitionCost: 'pattern' }, { ...sent, acquisitionCost: 'free' }).acquisitionCost).toBe(
      'Enter an amount in rand, for example 280.00.',
    )
    expect(plainCostMessage({ acquisitionCost: 'Below zero.' }, { ...sent, acquisitionCost: '-1.00' }).acquisitionCost).toBe('Below zero.')
  })
})

describe('the body of a change', () => {
  it('sends nothing when nothing changed', () => {
    expect(assetChangesFrom(SHELF_UNIT, draftOfAsset(SHELF_UNIT)).body).toEqual({})
  })

  it('sends only what changed, and null to clear', () => {
    const draft = { ...draftOfAsset(SHELF_UNIT), serialNumber: '', hourMeterReading: '413', conditionGrade: 'C' }

    expect(assetChangesFrom(SHELF_UNIT, draft).body).toEqual({ serialNumber: null, hourMeterReading: 413, conditionGrade: 'C' })
  })
})

describe('the words of a move', () => {
  it('names the four moves of the contract, and asks why for three of them', () => {
    expect(['AVAILABLE', 'UNDER_REPAIR', 'QUARANTINED', 'RETIRED'].map((to) => moveWords(to as 'AVAILABLE').action)).toEqual([
      'Commission it',
      'Send it for repair',
      'Quarantine it',
      'Retire it',
    ])
    expect(moveWords('AVAILABLE').asksForAReason).toBe(false)
    expect(moveWords('RETIRED').asksForAReason).toBe(true)
  })

  it('still offers a move it has no words for, by where the unit would stand', () => {
    expect(moveWords('INTAKE').action).toBe('Mark it being booked in, not hireable yet')
  })

  it('cuts every booking out of a sentence as a link to its checkout', () => {
    expect(sentenceWithBookings('Held for booking TSH-R-26-000124, so it cannot be retired.')).toEqual([
      { text: 'Held for booking ', href: null },
      { text: 'TSH-R-26-000124', href: '/counter/checkout/TSH-R-26-000124' },
      { text: ', so it cannot be retired.', href: null },
    ])
  })
})
