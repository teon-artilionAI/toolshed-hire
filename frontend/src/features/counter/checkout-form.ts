/**
 * The handover form of SC-14, the rules it is checked against, and the body
 * it is sent as.
 *
 * For each unit the assistant reads the asset tag off the unit, records the
 * condition it goes out in, what goes with it, and the hour meter when it has
 * one. Then the customer signs the hire agreement. The form holds that and
 * nothing else. The deposit and every other figure are the server's, and the
 * form never works one out.
 *
 * Every control has an id, and a problem is keyed by the id of the control it
 * is about, so a message lands under the right box whether it came from these
 * checks or from the API.
 */

import { MAX_ACCESSORIES_LENGTH } from '../../shared/api/checkout'
import type {
  CheckoutRequest,
  CheckoutUnit,
  ConditionGrade,
  ReservationCheckout,
} from '../../shared/api/contract'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { formatDate, money } from '../../shared/format'

/** What the assistant records about one unit. */
export interface UnitDraft {
  tagRead: boolean
  conditionOut: ConditionGrade
  accessories: string
  /** The hour meter as typed. Empty for a unit with no meter. */
  meter: string
}

export interface CheckoutDraft {
  /** Keyed by the allocation of each unit. */
  units: Record<string, UnitDraft>
  agreementSigned: boolean
}

/** A message for each control, keyed by the id of the control. */
export type CheckoutErrors = Readonly<Record<string, string>>

export type UnitControl = 'tag' | 'condition' | 'accessories' | 'meter'

/** The id of the agreement box. */
export const AGREEMENT_ID = 'checkout-agreement'

const WHOLE_NUMBER_PATTERN = /^\d+$/

/** The id of one control of one unit, by the unit's place on the reservation. */
export function unitControlId(index: number, control: UnitControl): string {
  return `unit-${index + 1}-${control}`
}

/** The form a checkout opens with. Each unit starts at the grade it has now,
 *  and a unit with a meter starts at its last reading. */
export function draftFor(checkout: ReservationCheckout): CheckoutDraft {
  return {
    units: Object.fromEntries(
      checkout.units.map((unit) => [
        unit.allocationId,
        {
          tagRead: false,
          conditionOut: unit.conditionGrade,
          accessories: '',
          meter: unit.hourMeter === null ? '' : String(unit.hourMeter),
        },
      ]),
    ),
    agreementSigned: false,
  }
}

function unitDraft(draft: CheckoutDraft, unit: CheckoutUnit): UnitDraft {
  const found = draft.units[unit.allocationId]
  if (!found) {
    throw new Error(
      `The checkout form has no answers for allocation ${unit.allocationId}. draftFor builds one ` +
        'for every unit, so the form was built for another reservation.',
    )
  }
  return found
}

/**
 * Check the form before it is sent. The API runs its own checks and has the
 * last word.
 *
 * @returns A sentence for each control that needs fixing.
 */
export function validateCheckout(checkout: ReservationCheckout, draft: CheckoutDraft): CheckoutErrors {
  const errors: Record<string, string> = {}
  checkout.units.forEach((unit, index) => {
    const answers = unitDraft(draft, unit)
    if (!answers.tagRead) {
      errors[unitControlId(index, 'tag')] =
        `Read the tag on the unit and tick it. If it does not say ${unit.assetTag}, stop and fetch the right unit.`
    }
    if (answers.accessories.trim().length > MAX_ACCESSORIES_LENGTH) {
      errors[unitControlId(index, 'accessories')] =
        `Keep the accessories to ${MAX_ACCESSORIES_LENGTH} characters. This has ${answers.accessories.trim().length}.`
    }
    if (unit.hourMeter !== null) {
      const typed = answers.meter.trim()
      if (!WHOLE_NUMBER_PATTERN.test(typed)) {
        errors[unitControlId(index, 'meter')] = 'Enter the reading on the hour meter, in whole hours.'
      } else if (Number(typed) < unit.hourMeter) {
        errors[unitControlId(index, 'meter')] =
          `The meter cannot read less than the last reading, ${unit.hourMeter} hours. Read it again.`
      }
    }
  })
  if (!draft.agreementSigned) {
    errors[AGREEMENT_ID] = 'The customer signs the hire agreement before anything leaves the counter.'
  }
  return errors
}

/**
 * The body the form is sent as. Every unit of the reservation exactly once,
 * with what was recorded about it, and the agreement signed.
 *
 * @throws Error when the agreement is not signed. `validateCheckout` refuses
 *   that form, so reaching here with it is a defect in the screen.
 */
export function toCheckoutRequest(checkout: ReservationCheckout, draft: CheckoutDraft): CheckoutRequest {
  if (!draft.agreementSigned) {
    throw new Error(
      'Tried to build a checkout body from a form whose agreement is not signed. ' +
        'validateCheckout refuses that form, so the screen should not have sent it.',
    )
  }
  return {
    items: checkout.units.map((unit) => {
      const answers = unitDraft(draft, unit)
      const accessories = answers.accessories.trim()
      return {
        allocationId: unit.allocationId,
        conditionOut: answers.conditionOut,
        accessoriesOut: accessories === '' ? null : accessories,
        hourMeterOut: unit.hourMeter === null ? null : Number(answers.meter.trim()),
      }
    }),
    agreementSigned: true,
  }
}

/**
 * The controls the API names a field of. A rule on the server may name a
 * field the way the backend spells it rather than the way the wire does, so
 * both spellings are read.
 */
const API_FIELD_CONTROL: Record<string, UnitControl> = {
  conditionOut: 'condition',
  condition_out: 'condition',
  accessoriesOut: 'accessories',
  accessories_out: 'accessories',
  hourMeterOut: 'meter',
  hour_meter_out: 'meter',
  allocationId: 'tag',
  allocation_id: 'tag',
}

/** The names the API may give the agreement. */
const AGREEMENT_FIELDS: readonly string[] = ['agreementSigned', 'agreement_signed']

/**
 * Put each message the API sent under the control it is about.
 *
 * @returns The messages keyed by control id, and the ones no control shows.
 */
export function serverErrorsByControl(fields: FieldErrors): { byControl: CheckoutErrors; leftOver: string[] } {
  const byControl: Record<string, string> = {}
  const leftOver: string[] = []
  for (const [name, message] of Object.entries(fields)) {
    const item = /^items\.(\d+)\.(\w+)$/.exec(name)
    const control = item ? API_FIELD_CONTROL[item[2]] : undefined
    if (item && control) byControl[unitControlId(Number(item[1]), control)] = message
    else if (AGREEMENT_FIELDS.includes(name)) byControl[AGREEMENT_ID] = message
    else leftOver.push(message)
  }
  return { byControl, leftOver }
}

/** What pressing the last button will do, in words, before it is pressed. */
export function handoverSentence(checkout: ReservationCheckout): string {
  const count = checkout.units.length
  const tags = checkout.units.map((unit) => unit.assetTag).join(', ')
  return (
    `${count} ${count === 1 ? 'unit' : 'units'}, ${tags}, will go out to ` +
    `${checkout.customer.displayName} from ${checkout.branchName}. A deposit of ` +
    `${money(checkout.depositTotal)} is recorded as taken, and the hire is due back on ` +
    `${formatDate(checkout.to)}.`
  )
}
