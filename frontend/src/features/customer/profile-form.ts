/**
 * The shape of the profile form on SC-09 and the rules it is checked against.
 *
 * The form holds the fields the API lets a customer change and no others.
 * Their email address, identity document, account standing, discount and
 * customer type are not here, because only a branch changes those.
 *
 * Only what the customer changed is checked and only that is sent. A field
 * they did not touch is already held by the server, so it is left as it is.
 */

import type { MyProfile, UpdateMyProfileRequest } from '../../shared/api/contract'
import {
  hasTwoNames,
  isMobileWellFormed,
  isPostalCodeWellFormed,
  stripSeparators,
} from './customer-rules'

/** What the form holds. A company name or VAT number the customer has not
 *  given is an empty box, and is sent as null. */
export interface ProfileDraft {
  fullName: string
  phone: string
  billingAddressLine1: string
  billingSuburb: string
  billingCity: string
  billingPostalCode: string
  companyName: string
  vatNumber: string
}

export type ProfileField = keyof ProfileDraft
export type ProfileErrors = Partial<Record<ProfileField, string>>

/** Reading order of the form. */
export const PROFILE_FIELD_ORDER: readonly ProfileField[] = [
  'fullName',
  'phone',
  'companyName',
  'vatNumber',
  'billingAddressLine1',
  'billingSuburb',
  'billingCity',
  'billingPostalCode',
]

/** The form as it opens, holding what the server holds. */
export function draftFrom(profile: MyProfile): ProfileDraft {
  return {
    fullName: profile.fullName,
    phone: profile.phone,
    billingAddressLine1: profile.billingAddressLine1,
    billingSuburb: profile.billingSuburb,
    billingCity: profile.billingCity,
    billingPostalCode: profile.billingPostalCode,
    companyName: profile.companyName ?? '',
    vatNumber: profile.vatNumber ?? '',
  }
}

/**
 * What the customer changed, as the body of the request.
 *
 * Spaces around a value are dropped and a phone number goes as digits. An
 * emptied company name or VAT number goes as null.
 *
 * @returns Only the members that differ from the profile. Empty when nothing
 *   was changed, and then there is nothing to send.
 */
export function changesIn(profile: MyProfile, draft: ProfileDraft): UpdateMyProfileRequest {
  const changes: UpdateMyProfileRequest = {}
  const fullName = draft.fullName.trim()
  if (fullName !== profile.fullName) changes.fullName = fullName
  const phone = stripSeparators(draft.phone)
  if (phone !== stripSeparators(profile.phone)) changes.phone = phone
  const billingAddressLine1 = draft.billingAddressLine1.trim()
  if (billingAddressLine1 !== profile.billingAddressLine1) {
    changes.billingAddressLine1 = billingAddressLine1
  }
  const billingSuburb = draft.billingSuburb.trim()
  if (billingSuburb !== profile.billingSuburb) changes.billingSuburb = billingSuburb
  const billingCity = draft.billingCity.trim()
  if (billingCity !== profile.billingCity) changes.billingCity = billingCity
  const billingPostalCode = draft.billingPostalCode.trim()
  if (billingPostalCode !== profile.billingPostalCode) {
    changes.billingPostalCode = billingPostalCode
  }
  const companyName = draft.companyName.trim() || null
  if (companyName !== profile.companyName) changes.companyName = companyName
  const vatNumber = draft.vatNumber.trim() || null
  if (vatNumber !== profile.vatNumber) changes.vatNumber = vatNumber
  return changes
}

/**
 * Check what the customer changed before it is sent.
 *
 * @param profile The profile as the server holds it.
 * @param draft What is in the form.
 * @returns A sentence for each changed field that needs fixing.
 */
export function validateProfileChanges(profile: MyProfile, draft: ProfileDraft): ProfileErrors {
  const changes = changesIn(profile, draft)
  const errors: ProfileErrors = {}

  if (changes.fullName !== undefined) {
    if (!changes.fullName) errors.fullName = 'Tell us your full name as it appears on your identity document.'
    else if (!hasTwoNames(changes.fullName)) errors.fullName = 'Give both your first name and your surname.'
  }
  if (changes.phone !== undefined) {
    if (!changes.phone) errors.phone = 'The counter phones this number when a hire is due back.'
    else if (!isMobileWellFormed(changes.phone)) {
      errors.phone = 'Enter ten digits starting with a zero, for example 082 441 7719.'
    }
  }
  if (changes.billingAddressLine1 === '') {
    errors.billingAddressLine1 = 'Enter the first line of the address we should bill to.'
  }
  if (changes.billingSuburb === '') errors.billingSuburb = 'Enter the suburb we should bill to.'
  if (changes.billingCity === '') errors.billingCity = 'Enter the city we should bill to.'
  if (changes.billingPostalCode !== undefined) {
    if (!changes.billingPostalCode) {
      errors.billingPostalCode = 'Enter the postal code of the billing address.'
    } else if (!isPostalCodeWellFormed(changes.billingPostalCode)) {
      errors.billingPostalCode = 'A South African postal code has four digits, for example 8001.'
    }
  }
  if (changes.companyName === null && profile.customerType === 'TRADE') {
    errors.companyName = 'A trade account needs the name of the company.'
  }
  return errors
}
