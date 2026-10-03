/**
 * The checks the customer forms run before anything is sent.
 *
 * They are the same checks the API runs, made early so a person hears about a
 * slip beside the field and not after a round trip. The API still has the last
 * word, and whatever it refuses is shown under the field it names.
 */

import { ID_DOCUMENT_LAST_LENGTH, MIN_PASSWORD_LENGTH } from '../../shared/api/account'

/** How many digits a South African postal code has. */
const POSTAL_CODE_DIGITS = 4

/** Strip the spaces and dashes people type into phone numbers. */
export function stripSeparators(value: string): string {
  return value.replace(/[\s-]/g, '')
}

export function isEmailWellFormed(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim())
}

/** Ten digits starting with a zero, which is how South Africans write a
 *  mobile number. Spaces and dashes are forgiven. */
export function isMobileWellFormed(value: string): boolean {
  return /^0\d{9}$/.test(stripSeparators(value))
}

/** Exactly four letters or digits, which is all of an identity document
 *  number that is ever asked for or kept. */
export function isDocumentEnding(value: string): boolean {
  return new RegExp(`^[A-Za-z0-9]{${ID_DOCUMENT_LAST_LENGTH}}$`).test(value.trim())
}

/** Four digits, which is how a South African postal code is written. */
export function isPostalCodeWellFormed(value: string): boolean {
  return new RegExp(`^\\d{${POSTAL_CODE_DIGITS}}$`).test(value.trim())
}

/** Whether a name has at least a first name and a surname. */
export function hasTwoNames(value: string): boolean {
  return value.trim().split(/\s+/).length >= 2
}

/**
 * The problem with a password, or undefined when it is fine.
 *
 * The one rule is the length, which is the rule the API applies.
 */
export function passwordProblem(value: string): string | undefined {
  if (!value.trim()) return 'Choose a password so you can sign in again later.'
  if (value.length < MIN_PASSWORD_LENGTH) {
    return `Passwords need at least ${MIN_PASSWORD_LENGTH} characters. Yours has ${value.length}.`
  }
  return undefined
}

/** The problem with the second typing of a password, or undefined when it matches. */
export function confirmationProblem(password: string, confirmation: string): string | undefined {
  if (!confirmation) return 'Type the password a second time so we know it was not a slip.'
  if (confirmation !== password) return 'The two passwords are not the same. Retype them both.'
  return undefined
}
