/**
 * Tests for the rules of the walk in form and the body it is sent as.
 *
 * Each rule is tried with the one answer that breaks it, so a test fails for
 * one reason. The body is held to exactly the members the contract names, and
 * never the whole document number.
 */

import { describe, expect, it } from 'vitest'
import { EMPTY_WALK_IN, toWalkInRequest, validateWalkIn, withValue } from './walkin-form'
import type { WalkInForm } from './walkin-form'

const FILLED: WalkInForm = {
  ...EMPTY_WALK_IN,
  displayName: '  Thandi Mokoena ',
  phone: '082 441-7719',
  idDocumentLast4: '508x',
  billingAddressLine1: ' 12 Loop Street',
  billingSuburb: 'Gardens',
  billingCity: 'Cape Town',
  billingPostalCode: '8001',
}

describe('checking a walk in', () => {
  it('passes a form filled in properly', () => {
    expect(validateWalkIn(FILLED)).toEqual({})
  })

  it.each<[keyof WalkInForm, string, RegExp]>([
    ['displayName', '', /full name/],
    ['displayName', 'Thandi', /first name and the surname/],
    ['phone', '', /mobile number is needed/],
    ['phone', '82 441 7719', /ten digits starting with a zero/],
    ['phone', '0824417719123', /ten digits starting with a zero/],
    ['idDocumentLast4', '', /last four characters/],
    ['idDocumentLast4', '9001015083086', /exactly four letters or digits/],
    ['idDocumentLast4', '50-3', /exactly four letters or digits/],
    ['billingAddressLine1', ' ', /first line of the address/],
    ['billingSuburb', '', /suburb/],
    ['billingCity', '', /city/],
    ['billingPostalCode', '', /postal code/],
    ['billingPostalCode', '80011', /four digits/],
  ])('refuses %s as "%s"', (field, value, message) => {
    const errors = validateWalkIn(withValue(FILLED, field, value))

    expect(Object.keys(errors)).toEqual([field])
    expect(errors[field]).toMatch(message)
  })

  it('asks for the company of a trade account, and not of anybody else', () => {
    const trade = withValue(FILLED, 'customerType', 'TRADE')

    expect(validateWalkIn(trade)).toEqual({ companyName: 'A trade account needs the name of the company.' })
    expect(validateWalkIn(withValue(trade, 'companyName', 'BuildRight'))).toEqual({})
  })

  it('ignores a document type or a customer type the menu does not offer', () => {
    expect(withValue(FILLED, 'idDocumentType', 'BIRTH_CERTIFICATE')).toBe(FILLED)
    expect(withValue(FILLED, 'customerType', 'COMPANY')).toBe(FILLED)
  })
})

describe('the body a walk in is sent as', () => {
  it('holds exactly the members the contract names, tidied, with the branch left to the server', () => {
    expect(toWalkInRequest(FILLED, null)).toEqual({
      displayName: 'Thandi Mokoena',
      phone: '0824417719',
      idDocumentType: 'SA_ID',
      idDocumentLast4: '508X',
      billingAddressLine1: '12 Loop Street',
      billingSuburb: 'Gardens',
      billingCity: 'Cape Town',
      billingPostalCode: '8001',
      customerType: 'INDIVIDUAL',
      companyName: null,
      vatNumber: null,
      branchCode: null,
    })
  })

  it('names the branch an administrator chose', () => {
    expect(toWalkInRequest(FILLED, 'SMW').branchCode).toBe('SMW')
  })

  it('sends the company and the VAT number only for a trade account', () => {
    const typedThenChanged = { ...FILLED, companyName: 'BuildRight', vatNumber: '4720318865' }

    expect(toWalkInRequest(typedThenChanged, null)).toMatchObject({ companyName: null, vatNumber: null })
    expect(toWalkInRequest({ ...typedThenChanged, customerType: 'TRADE' }, null)).toMatchObject({
      customerType: 'TRADE',
      companyName: 'BuildRight',
      vatNumber: '4720318865',
    })
    expect(toWalkInRequest({ ...typedThenChanged, customerType: 'TRADE', vatNumber: '  ' }, null).vatNumber).toBeNull()
  })
})
