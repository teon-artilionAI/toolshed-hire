/**
 * Tests for the rules of the profile form and the body a save is sent as.
 *
 * Only what the customer changed is checked and only that is sent, so each
 * test starts from the profile the server holds and changes one thing.
 */

import { describe, expect, it } from 'vitest'
import { PROFILE } from '../../test/account-samples'
import type { MyProfile } from '../../shared/api/contract'
import { changesIn, draftFrom, validateProfileChanges } from './profile-form'
import type { ProfileDraft } from './profile-form'

const TRADE: MyProfile = {
  ...PROFILE,
  customerType: 'TRADE',
  companyName: 'BuildRight Construction',
  vatNumber: '4123456789',
}

function draftWith(change: Partial<ProfileDraft>, profile: MyProfile = PROFILE): ProfileDraft {
  return { ...draftFrom(profile), ...change }
}

describe('what a save sends', () => {
  it('is nothing at all when nothing was changed', () => {
    expect(changesIn(PROFILE, draftFrom(PROFILE))).toEqual({})
    expect(changesIn(TRADE, draftFrom(TRADE))).toEqual({})
  })

  it('is only the members that differ, with the spaces around them dropped', () => {
    const draft = draftWith({ fullName: ' Wesley J Adonis ', billingCity: 'Bellville' })

    expect(changesIn(PROFILE, draft)).toEqual({ fullName: 'Wesley J Adonis', billingCity: 'Bellville' })
  })

  it('does not count a phone number retyped with spaces as a change', () => {
    expect(changesIn(PROFILE, draftWith({ phone: '082 441 7719' }))).toEqual({})
    expect(changesIn(PROFILE, draftWith({ phone: '083 555 0199' }))).toEqual({ phone: '0835550199' })
  })

  it('sends an emptied company name or VAT number as null', () => {
    expect(changesIn(TRADE, draftWith({ companyName: '  ', vatNumber: '' }, TRADE))).toEqual({
      companyName: null,
      vatNumber: null,
    })
  })

  it('never names a member the API does not let a customer change', () => {
    const everything = draftWith({
      fullName: 'A B',
      phone: '0835550199',
      billingAddressLine1: '1 New Road',
      billingSuburb: 'Observatory',
      billingCity: 'Bellville',
      billingPostalCode: '7925',
      companyName: 'A Company',
      vatNumber: '4000000000',
    })

    expect(Object.keys(changesIn(PROFILE, everything)).sort()).toEqual([
      'billingAddressLine1',
      'billingCity',
      'billingPostalCode',
      'billingSuburb',
      'companyName',
      'fullName',
      'phone',
      'vatNumber',
    ])
  })
})

describe('the rules of the profile form', () => {
  it('finds nothing wrong with a form that was not changed', () => {
    expect(validateProfileChanges(PROFILE, draftFrom(PROFILE))).toEqual({})
  })

  it('leaves alone a field the customer did not touch, whatever the server holds in it', () => {
    // An older profile with no postal code. Changing the phone must still save.
    const older: MyProfile = { ...PROFILE, billingPostalCode: '' }

    expect(validateProfileChanges(older, draftWith({ phone: '0835550199' }, older))).toEqual({})
  })

  it.each([
    [{ fullName: '' }, 'fullName', /full name/],
    [{ fullName: 'Wesley' }, 'fullName', /first name and your surname/],
    [{ phone: '' }, 'phone', /phones this number/],
    [{ phone: '12345' }, 'phone', /ten digits starting with a zero/],
    [{ billingAddressLine1: ' ' }, 'billingAddressLine1', /first line/],
    [{ billingSuburb: '' }, 'billingSuburb', /suburb/],
    [{ billingCity: '' }, 'billingCity', /city/],
    [{ billingPostalCode: '' }, 'billingPostalCode', /postal code/],
    [{ billingPostalCode: '80' }, 'billingPostalCode', /four digits/],
  ] as const)('refuses %j', (change, field, message) => {
    expect(validateProfileChanges(PROFILE, draftWith(change))[field]).toMatch(message)
  })

  it('lets an individual leave the company name empty, and not a trade account', () => {
    expect(validateProfileChanges(PROFILE, draftWith({ companyName: '' }))).toEqual({})
    expect(validateProfileChanges(TRADE, draftWith({ companyName: '' }, TRADE)).companyName).toMatch(
      /trade account needs the name/,
    )
  })
})
