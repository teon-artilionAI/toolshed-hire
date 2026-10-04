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
  plainMoneyMessages,
} from './model-form'

/** What the API says about money it could not read, in its framework's words. */
const PATTERN_MESSAGE = "String should match pattern '^-?\\d{1,10}(\\.\\d{1,2})?$'"

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

describe("the server's messages about money", () => {
  it('puts a figure that is not an amount at all in plain words, under the same field', () => {
    const fields = { dailyRate: PATTERN_MESSAGE, slug: 'That name in the web address is already in use.' }

    expect(plainMoneyMessages(fields, { dailyRate: 'fifty' })).toEqual({
      dailyRate: 'Enter an amount in rand, for example 280.00.',
      slug: 'That name in the web address is already in use.',
    })
  })

  it('says an amount with more digits than the API reads is too large', () => {
    expect(plainMoneyMessages({ replacementValue: PATTERN_MESSAGE }, { replacementValue: '12345678901.00' })).toEqual({
      replacementValue: 'Enter an amount of at most R9,999,999,999.99.',
    })
  })

  it("keeps the server's own sentence about an amount it could read", () => {
    const fields = { depositAmount: 'Enter an amount of zero or more.' }

    expect(plainMoneyMessages(fields, { depositAmount: '-1.00' })).toEqual(fields)
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
