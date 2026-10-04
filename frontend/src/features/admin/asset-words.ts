/**
 * The words SC-21 uses for what the server sends about a unit, and where a
 * reference in it leads.
 *
 * The moves a unit may make are the server's, in `allowedTransitions`. This
 * file only says each one in words, the button that offers it, the question
 * before it and what it does, and whether the screen asks for a reason. The
 * contract asks for one before a unit is sent for repair, quarantined or
 * retired. A status the server offers that has no words of its own here is
 * still offered, named by where the unit would then stand.
 *
 * A booking, a hire or a damage report named by the server is a link to the
 * screen where it is dealt with, because the owner reaches the counter
 * screens as well. The server names a booking inside the sentence of a 409,
 * so the sentence is cut at each reference of a booking it holds.
 */

import type { AdminAsset, AssetHistoryEntry, AssetHistoryKind, AssetStatus } from '../../shared/api/contract'
import { ASSET_STATUS_LABEL } from '../counter/counter-labels'
import { checkoutHref, damageHref, rentalHref } from '../counter/counter-links'
import { NO_TRAIL_FILTERS, writeTrailFilters } from './audit-address'
import { AUDIT_LOG_PATH } from './admin-links'

/** How one move by hand is put to the owner. */
export interface MoveWords {
  /** The button that offers the move, for example "Retire it". */
  action: string
  /** The question before it, with the tag in it. */
  question: (tag: string) => string
  /** The button that sends it. */
  answer: string
  /** The same button while it is in flight. */
  pending: string
  /** What the move does, in a sentence or two. */
  consequence: (unit: AdminAsset) => string
  /** Whether the owner is asked why. */
  asksForAReason: boolean
}

const NAMED_MOVES: Partial<Record<AssetStatus, MoveWords>> = {
  AVAILABLE: {
    action: 'Commission it',
    question: (tag) => `Commission ${tag}?`,
    answer: 'Yes, commission it',
    pending: 'Commissioning it',
    consequence: (unit) => `It goes on the shelf at ${unit.branchName}, and it can be booked and hired out.`,
    asksForAReason: false,
  },
  UNDER_REPAIR: {
    action: 'Send it for repair',
    question: (tag) => `Send ${tag} for repair?`,
    answer: 'Yes, send it for repair',
    pending: 'Sending it for repair',
    consequence: () => 'It goes to the workshop, and nobody can book it until it is commissioned again.',
    asksForAReason: true,
  },
  QUARANTINED: {
    action: 'Quarantine it',
    question: (tag) => `Quarantine ${tag}?`,
    answer: 'Yes, quarantine it',
    pending: 'Quarantining it',
    consequence: () => 'It is held back until somebody has inspected it, and nobody can book it meanwhile.',
    asksForAReason: true,
  },
  RETIRED: {
    action: 'Retire it',
    question: (tag) => `Retire ${tag}?`,
    answer: 'Yes, retire it',
    pending: 'Retiring it',
    consequence: () =>
      'It leaves the fleet for good and can never be booked or hired out again. Its row and its whole history are kept, because nothing is ever deleted.',
    asksForAReason: true,
  },
}

/** The words of a move. One the server offers with no words of its own here is
 *  named by where the unit would then stand. */
export function moveWords(to: AssetStatus): MoveWords {
  const named = NAMED_MOVES[to]
  if (named !== undefined) return named
  const standing = ASSET_STATUS_LABEL[to].toLowerCase()
  return {
    action: `Mark it ${standing}`,
    question: (tag) => `Mark ${tag} ${standing}?`,
    answer: 'Yes, mark it',
    pending: 'Marking it',
    consequence: () => `It will stand as ${standing}.`,
    asksForAReason: false,
  }
}

/** What each kind of history entry is about. */
export const HISTORY_KIND_LABEL: Record<AssetHistoryKind, string> = {
  ALLOCATION: 'Booking',
  RENTAL: 'Hire',
  DAMAGE_REPORT: 'Damage report',
  AUDIT_EVENT: 'Register',
}

/** A link from an entry of the history, with its words. */
export interface ReferenceLink {
  href: string
  label: string
}

/**
 * Where the reference of a history entry leads. A booking opens at its
 * checkout, a hire at its return and a damage report on the damage screen of
 * the unit. An entry of the register's own trail has no screen of its own.
 */
export function historyLink(entry: AssetHistoryEntry, tag: string): ReferenceLink | null {
  if (entry.reference === null) return null
  switch (entry.kind) {
    case 'ALLOCATION':
      return { href: checkoutHref(entry.reference), label: `Open booking ${entry.reference}` }
    case 'RENTAL':
      return { href: rentalHref(entry.reference), label: `Open hire ${entry.reference}` }
    case 'DAMAGE_REPORT':
      return { href: damageHref(tag), label: `Open damage report ${entry.reference}` }
    case 'AUDIT_EVENT':
      return null
  }
}

/** SC-24 narrowed to the events of one unit, by its key. */
export function unitTrailHref(unit: AdminAsset): string {
  const query = writeTrailFilters({ ...NO_TRAIL_FILTERS, entityType: 'asset', entityId: unit.id })
  return `${AUDIT_LOG_PATH}?${query.toString()}`
}

/** A booking reference as the server prints it, for example TSH-R-26-000124. */
const BOOKING_REFERENCE = /(TSH-R-\d{2}-\d{6,})/

/** One piece of a sentence. A booking it names is a link to its checkout. */
export type SentencePart = { text: string; href: null } | { text: string; href: string }

/** A sentence of the server's cut at every booking it names, each a link. */
export function sentenceWithBookings(sentence: string): SentencePart[] {
  return sentence
    .split(BOOKING_REFERENCE)
    .filter((piece) => piece !== '')
    .map((piece) => (BOOKING_REFERENCE.test(piece) ? { text: piece, href: checkoutHref(piece) } : { text: piece, href: null }))
}
