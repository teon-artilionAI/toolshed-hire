/**
 * The shape of the registration form and the rules it is checked against.
 *
 * Kept beside the screen rather than inside it so the rules can be read on
 * their own. Every message says what is wrong and what to do about it,
 * because "invalid input" tells a person at a counter nothing.
 *
 * Each field carries the name the API gives it, so a message the API sends
 * about a field lands under that field with no table in between.
 *
 * The form asks for the last four characters of the identity document and
 * never for the whole number. The counter checks the full document when the
 * equipment is collected, and four characters are enough to match it then.
 *
 * Nothing here knows which email addresses have accounts. The API answers a
 * registration the same way whether the address is new or not, and the
 * browser has no list to look in.
 */

import { ID_DOCUMENT_TYPES } from '../../shared/api/account'
import type { IdDocumentType, RegisterRequest } from '../../shared/api/contract'
import {
  confirmationProblem,
  hasTwoNames,
  isDocumentEnding,
  isEmailWellFormed,
  isMobileWellFormed,
  isPostalCodeWellFormed,
  passwordProblem,
  stripSeparators,
} from './customer-rules'

export interface RegistrationForm {
  fullName: string
  email: string
  phone: string
  idDocumentType: IdDocumentType
  idDocumentLast4: string
  billingAddressLine1: string
  billingSuburb: string
  billingCity: string
  billingPostalCode: string
  /** Empty until the person chooses, and then the first branch stands in. */
  homeBranchCode: string
  password: string
  confirmPassword: string
  acceptsPrivacyNotice: boolean
}

export type RegistrationField = keyof RegistrationForm
export type RegistrationErrors = Partial<Record<RegistrationField, string>>

/** The fields a person types or chooses text for. */
export type TextFieldName = Exclude<RegistrationField, 'acceptsPrivacyNotice'>

export const EMPTY_REGISTRATION: RegistrationForm = {
  fullName: '',
  email: '',
  phone: '',
  idDocumentType: 'SA_ID',
  idDocumentLast4: '',
  billingAddressLine1: '',
  billingSuburb: '',
  billingCity: 'Cape Town',
  billingPostalCode: '',
  homeBranchCode: '',
  password: '',
  confirmPassword: '',
  acceptsPrivacyNotice: false,
}

/** Reading order of the form, which is also the order problems are listed
 *  in the summary above it. */
export const REGISTRATION_FIELD_ORDER: readonly RegistrationField[] = [
  'fullName',
  'email',
  'phone',
  'idDocumentType',
  'idDocumentLast4',
  'billingAddressLine1',
  'billingSuburb',
  'billingCity',
  'billingPostalCode',
  'homeBranchCode',
  'password',
  'confirmPassword',
  'acceptsPrivacyNotice',
]

/**
 * The form after one text box or menu has changed.
 *
 * @param value What was typed or chosen. A document type the menu does not
 *   offer changes nothing.
 */
export function withText(
  form: RegistrationForm,
  field: TextFieldName,
  value: string,
): RegistrationForm {
  if (field === 'idDocumentType') {
    const type = ID_DOCUMENT_TYPES.find((known) => known === value)
    return type === undefined ? form : { ...form, idDocumentType: type }
  }
  return { ...form, [field]: value }
}

/**
 * Check the form before it is sent.
 *
 * @param form What was typed.
 * @param branchCodes The codes of the branches the API lists. Empty while the
 *   list has not arrived, and then no branch can be chosen.
 * @returns A sentence for each field that needs fixing.
 */
export function validateRegistration(
  form: RegistrationForm,
  branchCodes: readonly string[],
): RegistrationErrors {
  const errors: RegistrationErrors = {}

  if (!form.fullName.trim()) {
    errors.fullName = 'Tell us your full name as it appears on your identity document.'
  } else if (!hasTwoNames(form.fullName)) {
    errors.fullName = 'Give both your first name and your surname.'
  }

  if (!form.email.trim()) {
    errors.email = 'We send booking confirmations by email, so we need one.'
  } else if (!isEmailWellFormed(form.email)) {
    errors.email = 'That email address is missing an @ or a domain. Check it and try again.'
  }

  if (!form.phone.trim()) {
    errors.phone = 'The counter phones this number when your hire is due back.'
  } else if (!isMobileWellFormed(form.phone)) {
    errors.phone = 'Enter ten digits starting with a zero, for example 082 441 7719.'
  }

  if (!form.idDocumentLast4.trim()) {
    errors.idDocumentLast4 =
      'Enter the last four characters of the document number. The counter checks the full document at collection.'
  } else if (!isDocumentEnding(form.idDocumentLast4)) {
    errors.idDocumentLast4 =
      'Enter exactly four letters or digits. They are the last four of the document number, never the whole number.'
  }

  if (!form.billingAddressLine1.trim()) {
    errors.billingAddressLine1 = 'Enter the first line of the address we should bill to.'
  }
  if (!form.billingSuburb.trim()) {
    errors.billingSuburb = 'Enter the suburb we should bill to.'
  }
  if (!form.billingCity.trim()) {
    errors.billingCity = 'Enter the city we should bill to.'
  }
  if (!form.billingPostalCode.trim()) {
    errors.billingPostalCode = 'Enter the postal code of the billing address.'
  } else if (!isPostalCodeWellFormed(form.billingPostalCode)) {
    errors.billingPostalCode = 'A South African postal code has four digits, for example 8001.'
  }

  if (!branchCodes.includes(form.homeBranchCode)) {
    errors.homeBranchCode = 'Choose the branch you will usually collect from.'
  }

  const passwordIssue = passwordProblem(form.password)
  if (passwordIssue) errors.password = passwordIssue

  const confirmationIssue = confirmationProblem(form.password, form.confirmPassword)
  if (confirmationIssue) errors.confirmPassword = confirmationIssue

  if (!form.acceptsPrivacyNotice) {
    errors.acceptsPrivacyNotice =
      'You need to accept the privacy notice before we can open an account.'
  }

  return errors
}

/**
 * The body the form is sent as.
 *
 * Exactly the members the API asks for and no other. The second typing of the
 * password stays in the browser. Spaces around a value are dropped, a phone
 * number goes as digits, and the document ending goes in capitals, which is
 * how the counter reads it off the document.
 */
export function toRegisterRequest(form: RegistrationForm): RegisterRequest {
  return {
    email: form.email.trim(),
    password: form.password,
    fullName: form.fullName.trim(),
    phone: stripSeparators(form.phone),
    idDocumentType: form.idDocumentType,
    idDocumentLast4: form.idDocumentLast4.trim().toUpperCase(),
    billingAddressLine1: form.billingAddressLine1.trim(),
    billingSuburb: form.billingSuburb.trim(),
    billingCity: form.billingCity.trim(),
    billingPostalCode: form.billingPostalCode.trim(),
    homeBranchCode: form.homeBranchCode,
    acceptsPrivacyNotice: form.acceptsPrivacyNotice,
  }
}
