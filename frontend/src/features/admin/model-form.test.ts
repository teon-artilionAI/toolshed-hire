/**
 * Tests for the bodies the SC-20 forms are sent as. A new model or category
 * sends every field, a change sends only what differs from what the server
 * holds, money goes with two decimals by its digits, and the forms check
 * nothing but what they need to write a body.
 */

import { describe, expect, it } from 'vitest'
import { BREAKING, HAMMER, HAMMERS, WELDING } from '../../test/admin-catalogue-samples'
import { categoryChangesFrom, draftOfCategory, newCategoryRequestFrom, parentChoices } from './category-form'
import {
  EMPTY_MODEL_DRAFT,
  draftOfModel,
  modelChangesFrom,
  moneyChangesIn,
  moneyForTheWire,
  movesAFigure,
  newModelRequestFrom,
} from './model-form'

describe('money for the wire', () => {
  it.each([
    ['51', '51.00'],
    ['51.5', '51.50'],
    ['51,05', '51.05'],
    [' 0051.00 ', '51.00'],
    ['-5', '-5.00'],
  ])('writes %s as %s', (typed, sent) => {
    expect(moneyForTheWire(typed)).toBe(sent)
  })

  it('sends what is not an amount as it was typed, for the server to refuse', () => {
    expect(moneyForTheWire(' fifty ')).toBe('fifty')
    expect(moneyForTheWire('51.005')).toBe('51.005')
  })
})

describe('the model form', () => {
  it('sends nothing for a model nobody changed', () => {
    expect(modelChangesFrom(HAMMER, draftOfModel(HAMMER))).toEqual({ body: {}, errors: null })
  })

  it('sends only what changed, with a cleared description as null', () => {
    const draft = { ...draftOfModel({ ...HAMMER, longDescription: 'Old words.' }), lateFeePerDay: '51', longDescription: ' ' }

    const checked = modelChangesFrom({ ...HAMMER, longDescription: 'Old words.' }, draft)

    expect(checked.body).toEqual({ lateFeePerDay: '51.00', longDescription: null })
    expect(movesAFigure(checked.body ?? {})).toBe(true)
    expect(moneyChangesIn(HAMMER, checked.body ?? {})).toEqual([{ field: 'lateFeePerDay', before: '50.00', after: '51.00' }])
  })

  it('treats the same amount written another way as unchanged', () => {
    expect(modelChangesFrom(HAMMER, { ...draftOfModel(HAMMER), dailyRate: '280' }).body).toEqual({})
  })

  it('holds back only a missing category and days that are not whole numbers', () => {
    const checked = newModelRequestFrom({ ...EMPTY_MODEL_DRAFT, minHireDays: '1.5', maxHireDays: '28' })

    expect(checked.body).toBeNull()
    expect(checked.errors).toEqual({
      categoryId: 'Choose the category the model sits in.',
      minHireDays: 'Enter a whole number of days, for example 1.',
    })
  })

  it('leaves every rule about money to the server', () => {
    const draft = { ...draftOfModel(HAMMER), sku: '', weeklyRate: '99999', depositAmount: '-1' }

    const checked = newModelRequestFrom({ ...draft, categoryId: HAMMERS.id })

    expect(checked.errors).toBeNull()
    expect(checked.body).toMatchObject({ sku: '', weeklyRate: '99999.00', depositAmount: '-1.00' })
  })
})

describe('the category form', () => {
  it('offers only top level categories as a parent, never the category itself', () => {
    expect(parentChoices([BREAKING, HAMMERS, WELDING], null)).toEqual([BREAKING, WELDING])
    expect(parentChoices([BREAKING, HAMMERS, WELDING], BREAKING.id)).toEqual([WELDING])
  })

  it('sends a new category with a top level parent as null', () => {
    const checked = newCategoryRequestFrom({ ...draftOfCategory(WELDING), code: 'WELD-2', sortOrder: ' 7 ' })

    expect(checked.body).toEqual({ code: 'WELD-2', name: 'Welding', slug: 'welding', description: null, parentCategoryId: null, sortOrder: 7 })
  })

  it('sends only what changed, and holds back a place that is not a whole number', () => {
    expect(categoryChangesFrom(HAMMERS, { ...draftOfCategory(HAMMERS), parentCategoryId: '' }).body).toEqual({
      parentCategoryId: null,
    })
    expect(categoryChangesFrom(HAMMERS, { ...draftOfCategory(HAMMERS), sortOrder: 'first' }).errors).toEqual({
      sortOrder: 'Enter a whole number, for example 10. Lower numbers come first.',
    })
  })
})
