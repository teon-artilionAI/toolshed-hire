/**
 * The shape of the registration form and the rules it is checked against.
 *
 * Kept beside the screen rather than inside it so the rules can be read on
 * their own. Every message says what is wrong and what to do about it,
 * because "invalid input" tells a person at a counter nothing.
 */

import { customers, users } from '../../shared/fixtures'
import type { BranchCode, CustomerProfile } from '../../shared/types'
import {
  isEmailWellFormed,
  isMobileWellFormed,
  isThirteenDigits,
  passwordProblem,
} from './customer-fields'
import { ID_DOC_LABEL } from './customer-labels'

export type IdDocType = CustomerProfile['idDocType']

export interface RegistrationForm {
  fullName: string
  email: string
  mobile: string
  idDocType: IdDocType
  idDocNumber: string
  billingSuburb: string
  billingCity: string
  homeBranch: BranchCode
  password: string
  confirmPassword: string
  acceptsTerms: boolean
}

export type RegistrationField = keyof RegistrationForm
export type RegistrationErrors = Partial<Record<RegistrationField, string>>

export const EMPTY_REGISTRATION: RegistrationForm = {
  fullName: '',
  email: '',
  mobile: '',
  idDocType: 'SA_ID',
  idDocNumber: '',
  billingSuburb: '',
  billingCity: 'Cape Town',
  homeBranch: 'CBD',
  password: '',
  confirmPassword: '',
  acceptsTerms: false,
}

/** Reading order of the form, which is also the order problems are listed
 *  in the summary above it. */
export const REGISTRATION_FIELD_ORDER: RegistrationField[] = [
  'fullName',
  'email',
  'mobile',
  'idDocNumber',
  'billingSuburb',
  'billingCity',
  'password',
  'confirmPassword',
  'acceptsTerms',
]

function emailAlreadyRegistered(email: string): boolean {
  const needle = email.trim().toLowerCase()
  return (
    customers.some((customer) => customer.email.toLowerCase() === needle) ||
    users.some((user) => user.email.toLowerCase() === needle)
  )
}

export function validateRegistration(form: RegistrationForm): RegistrationErrors {
  const errors: RegistrationErrors = {}

  if (!form.fullName.trim()) {
    errors.fullName = 'Tell us your full name as it appears on your ID.'
  } else if (form.fullName.trim().split(/\s+/).length < 2) {
    errors.fullName = 'Give both your first name and your surname.'
  }

  if (!form.email.trim()) {
    errors.email = 'We send booking confirmations by email, so we need one.'
  } else if (!isEmailWellFormed(form.email)) {
    errors.email =
      'That email address is missing an @ or a domain. Check it and try again.'
  } else if (emailAlreadyRegistered(form.email)) {
    errors.email =
      'An account already uses that email address. Sign in instead, or use another address.'
  }

  if (!form.mobile.trim()) {
    errors.mobile = 'The counter phones this number when your hire is due back.'
  } else if (!isMobileWellFormed(form.mobile)) {
    errors.mobile =
      'Enter ten digits starting with a zero, for example 082 441 7719.'
  }

  if (!form.idDocNumber.trim()) {
    errors.idDocNumber = `Enter your ${ID_DOC_LABEL[
      form.idDocType
    ].toLowerCase()} number. The counter checks it before releasing equipment.`
  } else if (form.idDocType === 'SA_ID' && !isThirteenDigits(form.idDocNumber)) {
    errors.idDocNumber =
      'A South African ID number has thirteen digits. Check the number and try again.'
  }

  if (!form.billingSuburb.trim()) {
    errors.billingSuburb = 'Enter the suburb we should bill to.'
  }
  if (!form.billingCity.trim()) {
    errors.billingCity = 'Enter the city we should bill to.'
  }

  const passwordIssue = passwordProblem(form.password)
  if (passwordIssue) errors.password = passwordIssue

  if (!form.confirmPassword) {
    errors.confirmPassword =
      'Type the password a second time so we know it was not a slip.'
  } else if (form.confirmPassword !== form.password) {
    errors.confirmPassword =
      'The two passwords are not the same. Retype them both.'
  }

  if (!form.acceptsTerms) {
    errors.acceptsTerms =
      'You need to accept the hire terms before we can open an account.'
  }

  return errors
}
