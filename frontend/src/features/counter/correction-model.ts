/**
 * The rules of the owner's corrections at the counter, before anything is
 * sent. A written reason for a waiver, a reversal, an adjustment or the
 * release of a unit, and the amount of an adjustment.
 *
 * The server checks the same things and answers a 422 naming the field, which
 * the forms put under the box. Checking first only saves the owner a round
 * trip for a reason left empty or an amount that is not money.
 *
 * The amount is the owner's own figure, typed in. It is written out with two
 * decimals the way the API takes money, by its digits and never through a
 * float, and nothing is worked out from it.
 */

import { MAX_REASON_LENGTH, MIN_REASON_LENGTH } from '../../shared/api/corrections'
import type { Money } from '../../shared/api/contract'
import { isNegativeMoney, isNoMoney } from '../../shared/format'

/** Said under every reason box. */
export const REASON_HELP = `Between ${MIN_REASON_LENGTH} and ${MAX_REASON_LENGTH} characters. It is kept with the change and in the audit trail.`

/** An amount as the owner may type it. An optional minus, rand, and up to two decimals. */
const TYPED_AMOUNT = /^(-?)(\d+)(?:[.,](\d{1,2}))?$/

const CENT_DIGITS = 2

/**
 * What is wrong with a reason, or null when it may be sent.
 *
 * @param reason What was typed. The spaces around it do not count.
 */
export function reasonProblem(reason: string): string | null {
  const given = reason.trim()
  if (given === '') return 'Write the reason, so whoever reads this hire later knows why.'
  if (given.length < MIN_REASON_LENGTH) {
    return `Write at least ${MIN_REASON_LENGTH} characters. This has ${given.length}.`
  }
  if (given.length > MAX_REASON_LENGTH) {
    return `Keep the reason to ${MAX_REASON_LENGTH} characters. This has ${given.length}.`
  }
  return null
}

/**
 * The amount as the API takes it, with two decimals, or null when what was
 * typed is not an amount of money.
 *
 * @param typed For example "150", "-150.5" or "-150,50".
 */
export function amountForTheWire(typed: string): Money | null {
  const match = TYPED_AMOUNT.exec(typed.trim())
  if (!match) return null
  const [, sign, rand, cents = ''] = match
  // Leading zeros are dropped by reading the rand as a whole number, exactly.
  return `${sign}${BigInt(rand).toString()}.${cents.padEnd(CENT_DIGITS, '0')}`
}

/**
 * What is wrong with the amount of an adjustment, or null when it may be sent.
 *
 * A settled hire is never charged more, so once the hire is settled the server
 * only takes an amount that gives money back and refuses any other with a
 * 409. That is said here before anything is sent.
 *
 * @param typed What was typed in the box.
 * @param hireSettled Whether the hire is settled, as the server last said.
 */
export function amountProblem(typed: string, hireSettled: boolean): string | null {
  if (typed.trim() === '') return 'Enter the amount, including VAT, for example 150.00 or -150.00.'
  const amount = amountForTheWire(typed)
  if (amount === null) return 'Enter rand and cents only, for example 150.00, with a minus in front to give money back.'
  if (isNoMoney(amount)) return 'An adjustment of nothing changes nothing. Enter an amount that is not zero.'
  if (hireSettled && !isNegativeMoney(amount)) {
    return 'This hire is settled, so it can only give money back. Put a minus in front, for example -150.00.'
  }
  return null
}
