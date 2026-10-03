/**
 * The damage form of SC-16, the rules it is checked against, the body it is
 * sent as, and the question it asks before anything is sent.
 *
 * The assistant records how bad the damage is, what is broken, what the repair
 * is expected to cost and whether the customer is charged. That last answer
 * has no default. Neither is chosen when the form opens, and the form is not
 * sent until one is (BR-40). When the customer is charged and the unit came
 * back on a hire, the form also takes the amount to recover, VAT inclusive.
 * The server holds that amount to the replacement value copied onto the
 * booking (BR-39) and has the last word on it.
 *
 * An amount is typed in rand and sent the way the API writes money, with two
 * decimals. It never passes through a float.
 *
 * A problem is keyed by the control it is about, so a message lands under the
 * right box whether it came from these checks or from the API.
 */

import type { DamageReport, DamageSeverity, FileDamageReportRequest, LocatedUnit, Money } from '../../shared/api/contract'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { money } from '../../shared/format'

/** What the assistant has recorded so far. */
export interface DamageDraft {
  severity: DamageSeverity | null
  description: string
  /** The repair estimate as typed. */
  estimate: string
  /** Null until the assistant chooses. There is no default (BR-40). */
  chargeable: boolean | null
  /** The amount to recover as typed. Only asked for on a hire. */
  recovery: string
}

export type DamageControl = 'severity' | 'description' | 'estimate' | 'chargeable' | 'recovery'

/** A message for each control that needs fixing. */
export type DamageErrors = Readonly<Partial<Record<DamageControl, string>>>

/** The id of each control, which is where a problem in the list above jumps to. */
export const DAMAGE_CONTROL_ID: Readonly<Record<DamageControl, string>> = {
  severity: 'damage-severity',
  description: 'damage-description',
  estimate: 'damage-estimate',
  chargeable: 'damage-chargeable',
  recovery: 'damage-recovery',
}

/** The form a unit opens with. Nothing is chosen. */
export const EMPTY_DAMAGE_DRAFT: DamageDraft = {
  severity: null,
  description: '',
  estimate: '',
  chargeable: null,
  recovery: '',
}

/** Rand as a person types it. Digits, then up to two decimals after a point or
 *  a comma. A rand sign and spaces are allowed and ignored. */
const TYPED_RAND = /^R?(\d+)(?:[.,](\d{1,2}))?$/i

const CENT_DIGITS = 2

/**
 * Read an amount typed in rand as money the way the API writes it.
 *
 * @returns For example "450.00" for "R 450", or null when it is not an amount.
 */
export function typedRand(typed: string): Money | null {
  const match = TYPED_RAND.exec(typed.replace(/\s/g, ''))
  if (!match) return null
  const whole = match[1].replace(/^0+(?=\d)/, '')
  return `${whole}.${(match[2] ?? '').padEnd(CENT_DIGITS, '0')}`
}

/** Whether an amount the API writes is more than nothing. */
function isAboveNothing(amount: Money): boolean {
  return /[1-9]/.test(amount)
}

/** Whether the form asks for an amount to recover. Only when the customer is
 *  charged and the unit came back on a hire. */
export function asksForRecovery(draft: DamageDraft, rentalItemId: string | null): boolean {
  return draft.chargeable === true && rentalItemId !== null
}

/**
 * Check the form before it is sent. The API runs its own checks and has the
 * last word.
 *
 * @returns A sentence for each control that needs fixing.
 */
export function validateDamage(draft: DamageDraft, rentalItemId: string | null): DamageErrors {
  const errors: Partial<Record<DamageControl, string>> = {}
  if (draft.severity === null) errors.severity = 'Choose how bad the damage is.'
  if (draft.description.trim() === '') {
    errors.description = 'Describe what is broken. The workshop works from this and nothing else.'
  }
  if (typedRand(draft.estimate) === null) {
    errors.estimate =
      'Enter the estimated repair cost in rand, for example 450.00. Put your best guess if the workshop has not quoted yet.'
  }
  if (draft.chargeable === null) {
    errors.chargeable = 'Choose whether the customer is charged. Neither answer is chosen for you.'
  }
  const recovery = typedRand(draft.recovery)
  if (asksForRecovery(draft, rentalItemId) && (recovery === null || !isAboveNothing(recovery))) {
    errors.recovery = 'Enter the amount to recover from the customer in rand, including VAT, for example 450.00.'
  }
  return errors
}

/**
 * The body the form is sent as. Every member is present, with null for what
 * does not apply.
 *
 * @throws Error when the form has not passed `validateDamage`. The screen only
 *   sends a form that has, so reaching here with one is a defect in the screen.
 */
export function toDamageRequest(
  assetTag: string,
  rentalItemId: string | null,
  draft: DamageDraft,
): FileDamageReportRequest {
  const estimate = typedRand(draft.estimate)
  const recovery = asksForRecovery(draft, rentalItemId) ? typedRand(draft.recovery) : null
  if (draft.severity === null || draft.chargeable === null || estimate === null) {
    throw new Error(
      `Tried to build a damage report body for ${assetTag} from a form that is not finished. ` +
        'validateDamage refuses that form, so the screen should not have sent it.',
    )
  }
  return {
    assetTag,
    rentalItemId,
    severity: draft.severity,
    description: draft.description.trim(),
    repairEstimate: estimate,
    chargeableToCustomer: draft.chargeable,
    recoveryAmount: recovery,
  }
}

/** How bad the damage is, said inside a sentence. */
const SEVERITY_IN_A_SENTENCE: Record<DamageSeverity, string> = {
  MINOR: 'minor',
  MAJOR: 'major',
  WRITE_OFF: 'too bad to be worth repairing',
}

/**
 * What pressing the last button will do, in words, before it is pressed. One
 * sentence for each thing that happens.
 */
export function damageSentences(unit: LocatedUnit, rentalItemId: string | null, draft: DamageDraft): string[] {
  const request = toDamageRequest(unit.assetTag, rentalItemId, draft)
  const onHire = rentalItemId !== null
  const sentences = [
    `A damage report is filed against ${unit.assetTag}, ${unit.modelName}, at ${unit.branchName}. ` +
      `The damage is ${SEVERITY_IN_A_SENTENCE[request.severity]}.`,
    unit.status === 'QUARANTINED'
      ? `${unit.assetTag} stays in quarantine and cannot be booked until the owner resolves the report.`
      : `${unit.assetTag} is quarantined and cannot be booked until the owner resolves the report.`,
    `The repair is estimated at ${money(request.repairEstimate)}.`,
  ]
  if (request.recoveryAmount !== null) {
    sentences.push(
      `The customer is charged ${money(request.recoveryAmount)}, including VAT, and it is withheld from the deposit ` +
        'of the hire. The server refuses an amount above the replacement value copied onto the booking.',
    )
  } else if (request.chargeableToCustomer) {
    sentences.push('The report records that the customer is to be charged. It belongs to no hire, so no charge is raised.')
  } else {
    sentences.push('The customer is not charged. Toolshed Hire absorbs the repair.')
  }
  if (onHire) {
    sentences.push('The deposit of the hire is settled as the report is filed, unless something else on it is still waiting.')
  }
  return sentences
}

/**
 * The replacement value a report may not recover more than, when the screen
 * knows it. The API sends it only on a report, so it is known when an earlier
 * report names the same unit of the same hire, whose booking it was copied onto.
 */
export function knownReplacementValue(reports: readonly DamageReport[], rentalItemId: string | null): Money | null {
  if (rentalItemId === null) return null
  return reports.find((report) => report.rentalItemId === rentalItemId)?.replacementValue ?? null
}

/**
 * The controls the API names a field of. A rule on the server may name a field
 * the way the backend spells it rather than the way the wire does, so both
 * spellings are read.
 */
const API_FIELD_CONTROL: Record<string, DamageControl> = {
  severity: 'severity',
  description: 'description',
  repairEstimate: 'estimate',
  repair_estimate: 'estimate',
  chargeableToCustomer: 'chargeable',
  chargeable_to_customer: 'chargeable',
  recoveryAmount: 'recovery',
  recovery_amount: 'recovery',
}

/**
 * Put each message the API sent under the control it is about.
 *
 * @param shown The controls on the screen. A message about one that is not,
 *   or about a field the form has no control for, is left over.
 * @returns The messages by control, and the ones no control shows.
 */
export function serverDamageErrors(
  fields: FieldErrors,
  shown: readonly DamageControl[],
): { byControl: DamageErrors; leftOver: string[] } {
  const byControl: Partial<Record<DamageControl, string>> = {}
  const leftOver: string[] = []
  for (const [name, message] of Object.entries(fields)) {
    const control = API_FIELD_CONTROL[name]
    if (control !== undefined && shown.includes(control)) byControl[control] = message
    else leftOver.push(message)
  }
  return { byControl, leftOver }
}
