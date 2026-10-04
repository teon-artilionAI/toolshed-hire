/**
 * The words SC-23 uses for staff accounts and for the moves of a customer's
 * standing.
 *
 * Every value here is the server's, said in words. Whether an account can
 * sign in, has proved its address, or is locked, and when the person last
 * signed in, are all fields of the account, and nothing is worked out from
 * them beyond saying whether a lock the server set has ended yet.
 *
 * A customer can be moved between the three standings the contract names, and
 * the screen offers the two the customer is not in. Each move says what it does
 * to the customer's bookings, and releasing a hold says the count of bookings
 * they did not collect is kept, with the server's count.
 */

import type { AccountStatus, AdminUser, CustomerSummary, StaffRole } from '../../shared/api/contract'
import { ACCOUNT_STATUSES } from '../../shared/api/account'
import { branchDateTime } from '../../shared/today'
import { countOf } from '../counter/counter-labels'

/** Each role in words. */
export const STAFF_ROLE_LABEL: Record<StaffRole, string> = {
  COUNTER_STAFF: 'Counter staff',
  ADMIN: 'Admin and owner',
}

/** What each role may do, said under the menu that chooses it. */
export const ROLE_HELP = 'Counter staff work at one branch. Admins see every branch, the reports, pricing and this screen.'

/** Said where an administrator's branch would be. */
export const EVERY_BRANCH = 'Every branch'

/** A pill for whether the account can sign in, so colour follows the words. */
export function signInPill(user: Pick<AdminUser, 'isActive'>): { status: string; label: string } {
  return user.isActive ? { status: 'AVAILABLE', label: 'Can sign in' } : { status: 'RETIRED', label: 'Deactivated' }
}

/** Whether the person has proved the address they sign in with. */
export function verifiedWords(user: Pick<AdminUser, 'emailVerified'>): string {
  return user.emailVerified ? 'Confirmed' : 'Not confirmed yet'
}

/**
 * Whether a lock the server set after too many failed sign ins still holds.
 *
 * @param now The moment to compare with. A test passes its own.
 */
export function lockWords(user: Pick<AdminUser, 'lockedUntil'>, now: Date = new Date()): string {
  if (user.lockedUntil === null || Date.parse(user.lockedUntil) <= now.getTime()) return 'Not locked'
  return `Locked until ${branchDateTime(user.lockedUntil)}`
}

/** When the person last signed in, in branch time. */
export function lastSignInWords(user: Pick<AdminUser, 'lastLoginAt'>): string {
  return user.lastLoginAt === null ? 'Never signed in' : branchDateTime(user.lastLoginAt)
}

/** The branch an account belongs to, by the name the API gives it. */
export function branchWords(branchCode: string | null, nameOf: (code: string) => string): string {
  return branchCode === null ? EVERY_BRANCH : nameOf(branchCode)
}

/** The words of one move of a customer's standing. */
export interface StandingMoveWords {
  /** The button that opens the question. */
  action: string
  question: string
  /** What the move does to the customer's bookings. */
  consequence: string
  answer: string
  pending: string
  /** The title of the notice once the server has made the move. */
  outcome: string
  /** What the notice says under its title. */
  outcomeLine: string
}

function noShowsKept(customer: CustomerSummary): string {
  return `Their count of bookings not collected stays at ${customer.noShowCount}, because releasing a hold does not reset it.`
}

/**
 * The words of moving one customer to one standing.
 *
 * @param customer The customer as the server last sent them.
 * @param to The standing the move asks for.
 */
export function standingMoveWords(customer: CustomerSummary, to: AccountStatus): StandingMoveWords {
  const name = customer.displayName
  if (to === 'ON_HOLD') {
    return {
      action: 'Put on hold',
      question: `Put ${name} on hold?`,
      consequence: `${name} cannot make a new booking until the hold is released. Bookings already confirmed stay as they are, and nothing is cancelled.`,
      answer: 'Yes, put on hold',
      pending: 'Putting on hold',
      outcome: `${name} is on hold`,
      outcomeLine: 'They cannot make a new booking until the hold is released. The audit trail keeps the reason.',
    }
  }
  if (to === 'BLACKLISTED') {
    return {
      action: 'Blacklist',
      question: `Blacklist ${name}?`,
      consequence: `${name} cannot make a new booking at any branch until the blacklisting is lifted. Bookings already confirmed stay as they are, and nothing is cancelled.`,
      answer: 'Yes, blacklist',
      pending: 'Blacklisting',
      outcome: `${name} is blacklisted`,
      outcomeLine: 'They cannot make a new booking at any branch. The audit trail keeps the reason.',
    }
  }
  const wasBlacklisted = customer.accountStatus === 'BLACKLISTED'
  return {
    action: wasBlacklisted ? 'Lift the blacklisting' : 'Release the hold',
    question: wasBlacklisted ? `Lift the blacklisting of ${name}?` : `Release the hold on ${name}?`,
    consequence: `${name} can make new bookings again from now. ${noShowsKept(customer)}`,
    answer: wasBlacklisted ? 'Yes, lift it' : 'Yes, release the hold',
    pending: wasBlacklisted ? 'Lifting the blacklisting' : 'Releasing the hold',
    outcome: `${name} is in good standing again`,
    outcomeLine: `They can make new bookings again. ${noShowsKept(customer)}`,
  }
}

/** The standings a customer can be moved to, which are the ones they are not in. */
export function standingMoves(customer: CustomerSummary): AccountStatus[] {
  return ACCOUNT_STATUSES.filter((status) => status !== customer.accountStatus)
}

/** How many bookings the customer did not collect, in words. */
export function noShowWords(customer: CustomerSummary): string {
  return customer.noShowCount === 0 ? 'None' : countOf(customer.noShowCount, 'booking', 'bookings')
}
