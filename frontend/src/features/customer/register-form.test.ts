/**
 * Tests for the rules of the registration form and the body it is sent as.
 *
 * Each rule is checked on a form that is otherwise good, so a failure names
 * the one field that caused it.
 */

import { describe, expect, it } from 'vitest'
import {
  EMPTY_REGISTRATION,
  REGISTRATION_FIELD_ORDER,
  toRegisterRequest,
  validateRegistration,
  withText,
} from './register-form'
import type { RegistrationForm } from './register-form'

const BRANCH_CODES = ['CBD', 'BLV', 'SMW']

const GOOD: RegistrationForm = {
  fullName: 'Thandi Mokoena',
  email: 'thandi@example.co.za',
  phone: '082 441 7719',
  idDocumentType: 'SA_ID',
  idDocumentLast4: '5083',
  billingAddressLine1: '12 Loop Street',
  billingSuburb: 'Gardens',
  billingCity: 'Cape Town',
  billingPostalCode: '8001',
  homeBranchCode: 'CBD',
  password: 'twelve-chars',
  confirmPassword: 'twelve-chars',
  acceptsPrivacyNotice: true,
}

function errorsWith(change: Partial<RegistrationForm>) {
  return validateRegistration({ ...GOOD, ...change }, BRANCH_CODES)
}

describe('the rules of the registration form', () => {
  it('finds nothing wrong with a form that is filled in properly', () => {
    expect(validateRegistration(GOOD, BRANCH_CODES)).toEqual({})
  })

  it('asks for every answer on an empty form, in reading order', () => {
    const errors = validateRegistration(EMPTY_REGISTRATION, [])

    const missing = REGISTRATION_FIELD_ORDER.filter((field) => errors[field])
    expect(missing).toEqual([
      'fullName',
      'email',
      'phone',
      'idDocumentLast4',
      'billingAddressLine1',
      'billingSuburb',
      'billingPostalCode',
      'homeBranchCode',
      'password',
      'confirmPassword',
      'acceptsPrivacyNotice',
    ])
  })

  it.each([
    ['', /full name/],
    ['Thandi', /first name and your surname/],
  ])('wants a first name and a surname, given %j', (fullName, message) => {
    expect(errorsWith({ fullName }).fullName).toMatch(message)
  })

  it.each([
    ['', /we need one/],
    ['thandi.example.co.za', /missing an @ or a domain/],
    ['thandi@example', /missing an @ or a domain/],
  ])('wants a well formed email address, given %j', (email, message) => {
    expect(errorsWith({ email }).email).toMatch(message)
  })

  it('has no opinion on whether an address already has an account', () => {
    // The address of a seeded customer. The browser holds no list to find it in.
    expect(errorsWith({ email: 'w.adonis@buildright.co.za' }).email).toBeUndefined()
  })

  it.each([
    ['', /phones this number/],
    ['82 441 7719', /ten digits starting with a zero/],
    ['0824417', /ten digits starting with a zero/],
  ])('wants a ten digit mobile number, given %j', (phone, message) => {
    expect(errorsWith({ phone }).phone).toMatch(message)
  })

  it('forgives spaces and dashes in a mobile number', () => {
    expect(errorsWith({ phone: '082-441 7719' }).phone).toBeUndefined()
  })

  it.each([
    ['', /last four characters/],
    ['508', /exactly four letters or digits/],
    ['8703155800085', /never the whole number/],
    ['50-3', /exactly four letters or digits/],
  ])('wants exactly the last four of the document, given %j', (idDocumentLast4, message) => {
    expect(errorsWith({ idDocumentLast4 }).idDocumentLast4).toMatch(message)
  })

  it('takes letters in the last four, as a passport has', () => {
    expect(errorsWith({ idDocumentType: 'PASSPORT', idDocumentLast4: 'a9Z1' }).idDocumentLast4).toBeUndefined()
  })

  it.each([
    ['billingAddressLine1', /first line of the address/],
    ['billingSuburb', /suburb/],
    ['billingCity', /city/],
    ['billingPostalCode', /postal code/],
  ] as const)('wants %s filled in', (field, message) => {
    const form: RegistrationForm = { ...GOOD, [field]: '   ' }

    expect(validateRegistration(form, BRANCH_CODES)[field]).toMatch(message)
  })

  it.each(['800', '80011', 'ABCD'])('wants a four digit postal code, given %j', (billingPostalCode) => {
    expect(errorsWith({ billingPostalCode }).billingPostalCode).toMatch(/four digits/)
  })

  it('wants a branch the API lists', () => {
    expect(errorsWith({ homeBranchCode: 'BEL' }).homeBranchCode).toMatch(/Choose the branch/)
    expect(validateRegistration(GOOD, []).homeBranchCode).toMatch(/Choose the branch/)
  })

  it('wants a password of twelve characters or more, and nothing else of it', () => {
    expect(errorsWith({ password: '' }).password).toMatch(/Choose a password/)
    expect(errorsWith({ password: 'eleven-char' }).password).toBe(
      'Passwords need at least 12 characters. Yours has 11.',
    )
    // No digit and no capital. Twelve characters is the whole rule.
    expect(errorsWith({ password: 'abcdefghijkl', confirmPassword: 'abcdefghijkl' })).toEqual({})
  })

  it('wants the password typed the same way twice', () => {
    expect(errorsWith({ confirmPassword: '' }).confirmPassword).toMatch(/a second time/)
    expect(errorsWith({ confirmPassword: 'twelve-charz' }).confirmPassword).toMatch(/not the same/)
  })

  it('wants the privacy notice accepted', () => {
    expect(errorsWith({ acceptsPrivacyNotice: false }).acceptsPrivacyNotice).toMatch(
      /accept the privacy notice/,
    )
  })
})

describe('a change to one field of the form', () => {
  it('changes that field and no other', () => {
    expect(withText(GOOD, 'billingSuburb', 'Salt River')).toEqual({ ...GOOD, billingSuburb: 'Salt River' })
    expect(withText(GOOD, 'idDocumentType', 'PASSPORT')).toEqual({ ...GOOD, idDocumentType: 'PASSPORT' })
  })

  it('ignores a document type the menu does not offer', () => {
    expect(withText(GOOD, 'idDocumentType', 'LIBRARY_CARD')).toBe(GOOD)
  })
})

describe('the body a registration is sent as', () => {
  it('holds exactly the members the API asks for', () => {
    expect(toRegisterRequest(GOOD)).toEqual({
      email: 'thandi@example.co.za',
      password: 'twelve-chars',
      fullName: 'Thandi Mokoena',
      phone: '0824417719',
      idDocumentType: 'SA_ID',
      idDocumentLast4: '5083',
      billingAddressLine1: '12 Loop Street',
      billingSuburb: 'Gardens',
      billingCity: 'Cape Town',
      billingPostalCode: '8001',
      homeBranchCode: 'CBD',
      acceptsPrivacyNotice: true,
    })
  })

  it('never carries the second typing of the password or anything about standing', () => {
    const sent = Object.keys(toRegisterRequest(GOOD))

    expect(sent).toHaveLength(12)
    for (const member of ['confirmPassword', 'accountStatus', 'role', 'tradeDiscountPercent']) {
      expect(sent).not.toContain(member)
    }
  })

  it('drops the spaces around what was typed, and writes the document ending in capitals', () => {
    const sent = toRegisterRequest({
      ...GOOD,
      email: '  thandi@example.co.za ',
      fullName: ' Thandi Mokoena ',
      idDocumentType: 'PASSPORT',
      idDocumentLast4: ' a9z1 ',
      billingPostalCode: ' 8001 ',
    })

    expect(sent.email).toBe('thandi@example.co.za')
    expect(sent.fullName).toBe('Thandi Mokoena')
    expect(sent.idDocumentLast4).toBe('A9Z1')
    expect(sent.billingPostalCode).toBe('8001')
  })

  it('leaves the password exactly as it was typed', () => {
    expect(toRegisterRequest({ ...GOOD, password: '  spaced out pw  ' }).password).toBe('  spaced out pw  ')
  })
})
