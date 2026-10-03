/**
 * The return form of SC-15, the rules it is checked against, the body it is
 * sent as, and the question it asks before anything is sent.
 *
 * For each unit still out the assistant ticks whether it is back on the
 * counter, and records the grade it comes back at, the hour meter when it has
 * one, what came back with it, and whether to flag it for damage. The grade
 * starts at the one it went out at and the meter at its reading then, so a unit
 * that comes back as it left needs only the tick.
 *
 * The late fee is not here. It is the server's, from `daysLateToday` and
 * `lateFeeToday` on each unit, and the form neither works one out nor lets
 * anyone change one.
 *
 * Every control has an id, and a problem is keyed by the id of the control it
 * is about, so a message lands under the right box whether it came from these
 * checks or from the API.
 */

import { MAX_ACCESSORIES_LENGTH } from '../../shared/api/checkout'
import type { ConditionGrade, Rental, RentalItem, ReturnRequest } from '../../shared/api/contract'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { CONDITION_GRADES } from '../../shared/api/rental-read'
import { money } from '../../shared/format'
import { CONDITION_GRADE_LABEL, countOf } from './counter-labels'

/** What the assistant records about one unit still out. */
export interface ItemDraft {
  /** Ticked when the unit is back on the counter and is to be taken back now. */
  returning: boolean
  conditionIn: ConditionGrade
  /** The hour meter as typed. Empty for a unit with no meter. */
  meter: string
  accessories: string
  flaggedForDamage: boolean
}

/** Keyed by the rental item of each unit. */
export type ReturnDraft = Readonly<Record<string, ItemDraft>>

/** A message for each control, keyed by the id of the control. */
export type ReturnErrors = Readonly<Record<string, string>>

export type ItemControl = 'returning' | 'condition' | 'meter' | 'accessories' | 'damage'

/** Where the message goes when nothing is ticked. It is the list of units. */
export const UNITS_TO_RETURN_ID = 'return-units'

const WHOLE_NUMBER_PATTERN = /^\d+$/

/** The id of one control of one unit, by its rental item. */
export function itemControlId(itemId: string, control: ItemControl): string {
  return `return-${itemId}-${control}`
}

/** The units of a hire that are still out, in the order the hire lists them. */
export function itemsOut(rental: Rental): RentalItem[] {
  return rental.items.filter((item) => item.returnedAt === null)
}

/**
 * Whether a unit was recorded as lost rather than taken back.
 *
 * The API closes a lost unit with the time the loss was recorded and no grade,
 * and an item carries no flag that says lost. Every return carries a grade, so
 * a closed unit with none is a lost one. Its loss charges carry its id.
 */
export function isLost(item: RentalItem): boolean {
  return item.returnedAt !== null && item.conditionIn === null
}

/** How a unit is named at the counter. Its tag, or its model when there is none. */
export function itemLabel(item: RentalItem): string {
  return item.assetTag ?? item.modelName
}

function freshDraft(item: RentalItem): ItemDraft {
  return {
    returning: false,
    conditionIn: item.conditionOut,
    meter: item.hourMeterOut === null ? '' : String(item.hourMeterOut),
    accessories: '',
    flaggedForDamage: false,
  }
}

/** The form a hire opens with. Nothing is ticked. */
export function draftFor(rental: Rental): ReturnDraft {
  return Object.fromEntries(itemsOut(rental).map((item) => [item.id, freshDraft(item)]))
}

/** What was recorded for a unit, or how it starts when the hire was read again
 *  with a unit the form had not seen. */
export function answersFor(draft: ReturnDraft, item: RentalItem): ItemDraft {
  return draft[item.id] ?? freshDraft(item)
}

/** The units ticked to come back now, in the order the hire lists them. */
export function returningItems(rental: Rental, draft: ReturnDraft): RentalItem[] {
  return itemsOut(rental).filter((item) => answersFor(draft, item).returning)
}

/** A is the best grade, so a later letter is a worse unit. */
export function isWorse(now: ConditionGrade, before: ConditionGrade): boolean {
  return CONDITION_GRADES.indexOf(now) > CONDITION_GRADES.indexOf(before)
}

/**
 * Check the form before it is sent. The API runs its own checks and has the
 * last word.
 *
 * @returns A sentence for each control that needs fixing.
 */
export function validateReturn(rental: Rental, draft: ReturnDraft): ReturnErrors {
  const errors: Record<string, string> = {}
  const coming = returningItems(rental, draft)
  if (coming.length === 0) {
    errors[UNITS_TO_RETURN_ID] = 'Tick each unit that is back on the counter. Nothing is ticked yet.'
  }
  for (const item of coming) {
    const answers = answersFor(draft, item)
    const accessories = answers.accessories.trim()
    if (accessories.length > MAX_ACCESSORIES_LENGTH) {
      errors[itemControlId(item.id, 'accessories')] =
        `Keep the accessories to ${MAX_ACCESSORIES_LENGTH} characters. This has ${accessories.length}.`
    }
    if (item.hourMeterOut === null) continue
    const typed = answers.meter.trim()
    if (!WHOLE_NUMBER_PATTERN.test(typed)) {
      errors[itemControlId(item.id, 'meter')] = 'Enter the reading on the hour meter, in whole hours.'
    } else if (Number(typed) < item.hourMeterOut) {
      errors[itemControlId(item.id, 'meter')] =
        `The meter cannot read less than it did going out, ${item.hourMeterOut} hours. Read it again.`
    }
  }
  return errors
}

/**
 * The body the form is sent as. Each ticked unit once, with what was recorded
 * about it. The form has no box for notes, so they are always null.
 *
 * @throws Error when nothing is ticked. `validateReturn` refuses that form, so
 *   reaching here with it is a defect in the screen.
 */
export function toReturnRequest(rental: Rental, draft: ReturnDraft): ReturnRequest {
  const coming = returningItems(rental, draft)
  if (coming.length === 0) {
    throw new Error(
      `Tried to build a return body for ${rental.reference} with no unit ticked. ` +
        'validateReturn refuses that form, so the screen should not have sent it.',
    )
  }
  return {
    items: coming.map((item) => {
      const answers = answersFor(draft, item)
      const accessories = answers.accessories.trim()
      return {
        rentalItemId: item.id,
        conditionIn: answers.conditionIn,
        hourMeterIn: item.hourMeterOut === null ? null : Number(answers.meter.trim()),
        accessoriesIn: accessories === '' ? null : accessories,
        notes: null,
        flaggedForDamage: answers.flaggedForDamage,
      }
    }),
  }
}

/** "A", "A and B", or "A, B and C". */
function inWords(names: readonly string[]): string {
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/**
 * What pressing the last button will do, in words, before it is pressed. One
 * sentence for each thing that happens. Every late fee in it is the server's.
 */
export function returnSentences(rental: Rental, draft: ReturnDraft): string[] {
  const coming = returningItems(rental, draft)
  const sentences = [
    `${countOf(coming.length, 'unit', 'units')}, ${inWords(coming.map(itemLabel))}, ` +
      `${coming.length === 1 ? 'comes' : 'come'} back from ${rental.customerName} on ${rental.reference}.`,
  ]
  for (const item of coming) {
    const answers = answersFor(draft, item)
    if (isWorse(answers.conditionIn, item.conditionOut)) {
      sentences.push(
        `${itemLabel(item)} comes back at ${CONDITION_GRADE_LABEL[answers.conditionIn]}, worse than the ` +
          `${CONDITION_GRADE_LABEL[item.conditionOut]} it went out at.`,
      )
    }
    if (answers.flaggedForDamage) sentences.push(`${itemLabel(item)} is flagged for damage.`)
  }
  const late = coming.filter((item) => item.daysLateToday > 0)
  if (late.length === 0) sentences.push('Nothing coming back is late, so there is no late fee.')
  for (const item of late) {
    sentences.push(
      `${itemLabel(item)} is ${countOf(item.daysLateToday, 'day', 'days')} late, and the system charges a ` +
        `late fee of ${money(item.lateFeeToday)} for it, which is withheld from the deposit.`,
    )
  }
  const staying = itemsOut(rental).length - coming.length
  sentences.push(
    staying > 0
      ? `${countOf(staying, 'unit stays', 'units stay')} out, so the hire is partially returned and the deposit stays held.`
      : 'That is the last unit out, so the server settles the deposit as it records the return, unless something is still waiting.',
  )
  return sentences
}

/**
 * The controls the API names a field of. A rule on the server may name a field
 * the way the backend spells it rather than the way the wire does, so both
 * spellings are read.
 */
const API_FIELD_CONTROL: Record<string, ItemControl> = {
  rentalItemId: 'returning',
  rental_item_id: 'returning',
  conditionIn: 'condition',
  condition_in: 'condition',
  hourMeterIn: 'meter',
  hour_meter_in: 'meter',
  accessoriesIn: 'accessories',
  accessories_in: 'accessories',
  flaggedForDamage: 'damage',
  flagged_for_damage: 'damage',
}

/**
 * Put each message the API sent under the control it is about.
 *
 * @param sent The units in the order the body listed them, which is how the
 *   API numbers them.
 * @returns The messages keyed by control id, and the ones no control shows.
 */
export function serverErrorsByControl(
  fields: FieldErrors,
  sent: readonly RentalItem[],
): { byControl: ReturnErrors; leftOver: string[] } {
  const byControl: Record<string, string> = {}
  const leftOver: string[] = []
  for (const [name, message] of Object.entries(fields)) {
    const match = /^items\.(\d+)\.(\w+)$/.exec(name)
    const item = match ? sent[Number(match[1])] : undefined
    const control = match ? API_FIELD_CONTROL[match[2]] : undefined
    if (item && control) byControl[itemControlId(item.id, control)] = message
    else leftOver.push(message)
  }
  return { byControl, leftOver }
}
