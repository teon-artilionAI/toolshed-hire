/**
 * The walk in form of SC-12, and the rules it is checked against.
 *
 * A walk in is registered with a customer standing at the counter and a queue
 * behind them, so the form asks for what the API needs and nothing else. A
 * walk in has no login, so there is no email address and no password.
 *
 * The form asks for the last four characters of the identity document and
 * never for the whole number. The assistant checks the full document in their
 * hand and types only its ending, which is all the system keeps.
 *
 * Each field carries the name the API gives it, so a message the API sends
 * about a field lands under that field with no table in between. Every
 * message says what is wrong and what to do about it.
 */

import { ID_DOCUMENT_LAST_LENGTH, ID_DOCUMENT_TYPES, CUSTOMER_TYPES } from '../../shared/api/account'
import type { CustomerType, IdDocumentType, RegisterWalkInRequest } from '../../shared/api/contract'

/** How many digits a South African postal code has. */
export const POSTAL_CODE_DIGITS = 4

/** Ten digits starting with a zero, which is how a South African mobile is written. */
const MOBILE_PATTERN = /^0\d{9}$/

const DOCUMENT_ENDING_PATTERN = new RegExp(`^[A-Za-z0-9]{${ID_DOCUMENT_LAST_LENGTH}}$`)

const POSTAL_CODE_PATTERN = new RegExp(`^\\d{${POSTAL_CODE_DIGITS}}$`)

/** The city every branch trades in, which most walk ins live in too. */
export const DEFAULT_CITY = 'Cape Town'

export interface WalkInForm {
  displayName: string
  phone: string
  idDocumentType: IdDocumentType
  idDocumentLast4: string
  billingAddressLine1: string
  billingSuburb: string
  billingCity: string
  billingPostalCode: string
  customerType: CustomerType
  /** Asked for only for a trade account. */
  companyName: string
  /** Asked for only for a trade account, and optional there. */
  vatNumber: string
}

export type WalkInField = keyof WalkInForm
export type WalkInErrors = Partial<Record<WalkInField, string>>

export const EMPTY_WALK_IN: WalkInForm = {
  displayName: '',
  phone: '',
  idDocumentType: 'SA_ID',
  idDocumentLast4: '',
  billingAddressLine1: '',
  billingSuburb: '',
  billingCity: DEFAULT_CITY,
  billingPostalCode: '',
  customerType: 'INDIVIDUAL',
  companyName: '',
  vatNumber: '',
}

/** Reading order of the form, which is also the order problems are listed in. */
export const WALK_IN_FIELD_ORDER: readonly WalkInField[] = [
  'displayName',
  'phone',
  'customerType',
  'companyName',
  'vatNumber',
  'idDocumentType',
  'idDocumentLast4',
  'billingAddressLine1',
  'billingSuburb',
  'billingCity',
  'billingPostalCode',
]

/** Strip the spaces and dashes people type into phone numbers. */
function stripSeparators(value: string): string {
  return value.replace(/[\s-]/g, '')
}

/**
 * The form after one field has changed.
 *
 * @param value What was typed or chosen. A document type or a customer type
 *   the menu does not offer changes nothing.
 */
export function withValue(form: WalkInForm, field: WalkInField, value: string): WalkInForm {
  if (field === 'idDocumentType') {
    const type = ID_DOCUMENT_TYPES.find((known) => known === value)
    return type === undefined ? form : { ...form, idDocumentType: type }
  }
  if (field === 'customerType') {
    const type = CUSTOMER_TYPES.find((known) => known === value)
    return type === undefined ? form : { ...form, customerType: type }
  }
  return { ...form, [field]: value }
}

/**
 * Check the form before it is sent. The API runs the same checks and has the
 * last word.
 *
 * @returns A sentence for each field that needs fixing.
 */
export function validateWalkIn(form: WalkInForm): WalkInErrors {
  const errors: WalkInErrors = {}

  const name = form.displayName.trim()
  if (!name) {
    errors.displayName = 'Enter the full name as it appears on the identity document.'
  } else if (name.split(/\s+/).length < 2) {
    errors.displayName = 'Enter both the first name and the surname.'
  }

  if (!form.phone.trim()) {
    errors.phone = 'A mobile number is needed so the branch can reach them about the hire.'
  } else if (!MOBILE_PATTERN.test(stripSeparators(form.phone))) {
    errors.phone = 'Enter ten digits starting with a zero, for example 082 441 7719.'
  }

  if (form.customerType === 'TRADE' && !form.companyName.trim()) {
    errors.companyName = 'A trade account needs the name of the company.'
  }

  if (!form.idDocumentLast4.trim()) {
    errors.idDocumentLast4 =
      'Check the document and enter the last four characters of its number. The whole number is never kept.'
  } else if (!DOCUMENT_ENDING_PATTERN.test(form.idDocumentLast4.trim())) {
    errors.idDocumentLast4 = 'Enter exactly four letters or digits, the last four of the document number.'
  }

  if (!form.billingAddressLine1.trim()) {
    errors.billingAddressLine1 = 'Enter the first line of the address to bill.'
  }
  if (!form.billingSuburb.trim()) errors.billingSuburb = 'Enter the suburb of the address to bill.'
  if (!form.billingCity.trim()) errors.billingCity = 'Enter the city of the address to bill.'

  if (!form.billingPostalCode.trim()) {
    errors.billingPostalCode = 'Enter the postal code of the address to bill.'
  } else if (!POSTAL_CODE_PATTERN.test(form.billingPostalCode.trim())) {
    errors.billingPostalCode = 'A South African postal code has four digits, for example 8001.'
  }

  return errors
}

/**
 * The body the form is sent as.
 *
 * Exactly the members the API asks for. Spaces around a value are dropped, a
 * phone number goes as digits, and the document ending goes in capitals, the
 * way it is read off the document. The company and the VAT number go only for
 * a trade account.
 *
 * @param branchCode Null for counter staff, whose own branch is used. The
 *   branch an administrator chose, because an administrator has none.
 */
export function toWalkInRequest(form: WalkInForm, branchCode: string | null): RegisterWalkInRequest {
  const trade = form.customerType === 'TRADE'
  const vatNumber = form.vatNumber.trim()
  return {
    displayName: form.displayName.trim(),
    phone: stripSeparators(form.phone),
    idDocumentType: form.idDocumentType,
    idDocumentLast4: form.idDocumentLast4.trim().toUpperCase(),
    billingAddressLine1: form.billingAddressLine1.trim(),
    billingSuburb: form.billingSuburb.trim(),
    billingCity: form.billingCity.trim(),
    billingPostalCode: form.billingPostalCode.trim(),
    customerType: form.customerType,
    companyName: trade ? form.companyName.trim() : null,
    vatNumber: trade && vatNumber ? vatNumber : null,
    branchCode,
  }
}
