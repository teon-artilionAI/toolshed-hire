/**
 * The words SC-24 uses for what the server records.
 *
 * The trail names a record by its table and an action by a dotted name, such
 * as `reservation.confirmed`, and it keeps the fields that changed under the
 * names the backend gives them. The owner reads none of that. So each is
 * written out as words here, the known ones by hand and anything new by
 * turning the name into a phrase, so an action the backend adds later still
 * reads as words and never as a code.
 *
 * The values of a field are written out the same way. An instant reads as a
 * day and a time at the branches, and a word of the backend's own, such as
 * HELD, reads in lower case. Everything else is shown as it was recorded, and
 * nothing here works a figure out.
 */

import type { AuditActorRole, AuditEvent, AuditState, NotificationStatus } from '../../shared/api/contract'
import { branchDateTime } from '../../shared/today'

/** The records the trail is kept about, by the names the backend gives them,
 *  in the order the filter offers them. */
export const ENTITY_TYPE_LABEL: Readonly<Record<string, string>> = {
  reservation: 'Booking',
  rental: 'Hire',
  charge: 'Charge',
  allocation: 'Unit set aside for a booking',
  notification: 'Email',
  asset: 'Unit',
  damage_report: 'Damage report',
  customer_profile: 'Customer',
  user_account: 'Account',
}

/** Actions whose phrase made from the name would read badly. */
const ACTION_LABEL: Readonly<Record<string, string>> = {
  'auth.login_succeeded': 'Signed in',
  'auth.login_failed': 'Sign in refused',
  'auth.registered': 'Registered an account',
  'auth.registration_repeated': 'Tried to register an address already on file',
  'auth.email_verified': 'Confirmed an email address',
  'auth.verification_resent': 'Sent the email confirmation link again',
  'auth.password_reset_requested': 'Asked to reset a password',
  'auth.password_reset_completed': 'Reset a password',
  'auth.refresh_reuse_detected': 'A used sign in token was offered again, so every session was ended',
  'rental.checked_out': 'Hire checked out',
  'rental.items_returned': 'Units taken back',
  'rental.item_lost': 'Unit recorded as lost',
  'rental.overdue': 'Hire became overdue',
  'reservation.no_show': 'Booking marked as a no show',
  'customer.walk_in_registered': 'Walk in registered at the counter',
}

/** The role an event copied from the account that acted, in words. */
export const ACTOR_ROLE_LABEL: Record<AuditActorRole, string> = {
  CUSTOMER: 'customer',
  COUNTER_STAFF: 'counter staff',
  ADMIN: 'administrator',
}

/** Where an email stands, in words. */
export const NOTIFICATION_STATUS_LABEL: Record<NotificationStatus, string> = {
  QUEUED: 'Waiting to be sent',
  SENT: 'Sent',
  FAILED: 'Did not go out',
}

/** The status pill each email status is drawn with, so colour follows the words. */
export const NOTIFICATION_STATUS_PILL: Record<NotificationStatus, string> = {
  QUEUED: 'HELD',
  SENT: 'AVAILABLE',
  FAILED: 'OVERDUE',
}

/** Said of a recorded value that is null. */
const NOTHING = 'nothing'

/** An instant as the backend records it, ISO 8601 with a time of day. */
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/

/** A word of the backend's own, such as HELD or ITEMS_OUT. A code of three
 *  letters or fewer, such as a branch code, is kept as it is. */
const CODE_WORD = /^[A-Z]+(?:_[A-Z]+)*$/
const LONGEST_KEPT_CODE = 3

/** A recorded string as it reads. An instant is written at the branches, and a
 *  word of the backend's own in lower case words. */
function textWords(value: string): string {
  if (value === '') return 'empty'
  if (INSTANT.test(value) && !Number.isNaN(Date.parse(value))) return branchDateTime(value)
  if (CODE_WORD.test(value) && (value.includes('_') || value.length > LONGEST_KEPT_CODE)) {
    return value.replace(/_/g, ' ').toLowerCase()
  }
  return value
}

/** A name written by a program, such as `holdExpiresAt` or `deposit_held`, as
 *  lower case words. */
function nameAsWords(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_.-]+/g, ' ')
    .trim()
    .toLowerCase()
}

/** The first letter in capitals. */
function sentenceCase(words: string): string {
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** A kind of record in words, for example "Booking". */
export function entityTypeWords(entityType: string): string {
  return ENTITY_TYPE_LABEL[entityType] ?? sentenceCase(nameAsWords(entityType))
}

/** What happened in words, for example "Reservation confirmed". */
export function actionWords(action: string): string {
  return ACTION_LABEL[action] ?? sentenceCase(nameAsWords(action))
}

/** A field in words, for example "Hold expires at". */
export function fieldWords(field: string): string {
  return sentenceCase(nameAsWords(field))
}

/** Who acted, in words. An event with no person behind it was the system's. */
export function actorWords(event: Pick<AuditEvent, 'actorName' | 'actorRole'>): string {
  if (event.actorName === null) return 'the system, with no person behind it'
  return event.actorRole === null ? event.actorName : `${event.actorName}, ${ACTOR_ROLE_LABEL[event.actorRole]}`
}

/**
 * A value as it was recorded, in words. A list is written item by item and an
 * object field by field, so nothing is shown as raw JSON.
 */
export function valueWords(value: unknown): string {
  if (value === null || value === undefined) return NOTHING
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'string') return textWords(value)
  if (typeof value === 'number' || typeof value === 'bigint') return String(value)
  if (Array.isArray(value)) return value.length === 0 ? 'none' : value.map(valueWords).join(', ')
  if (typeof value === 'object') {
    const fields = Object.entries(value)
    if (fields.length === 0) return NOTHING
    return fields.map(([name, inner]) => `${nameAsWords(name)} ${valueWords(inner)}`).join('; ')
  }
  return String(value)
}

/** One field that changed, with how it read before and after. Null means the
 *  field was not recorded on that side. */
export interface FieldChange {
  field: string
  before: string | null
  after: string | null
}

/**
 * The fields that changed, in the order the server recorded them, the fields
 * after the change first. A field whose value is the same on both sides is
 * left out.
 */
export function changedFields(before: AuditState | null, after: AuditState | null): FieldChange[] {
  const was = before ?? {}
  const now = after ?? {}
  const names = [...Object.keys(now), ...Object.keys(was).filter((name) => !(name in now))]
  return names
    .filter((name) => !(name in was) || !(name in now) || JSON.stringify(was[name]) !== JSON.stringify(now[name]))
    .map((name) => ({
      field: fieldWords(name),
      before: name in was ? valueWords(was[name]) : null,
      after: name in now ? valueWords(now[name]) : null,
    }))
}

/** How one field changed, as a sentence. */
export function changeWords(change: FieldChange): string {
  if (change.before === null) return `Set to ${change.after ?? NOTHING}.`
  if (change.after === null) return `Was ${change.before}. No longer recorded.`
  return `Was ${change.before}. Now ${change.after}.`
}
