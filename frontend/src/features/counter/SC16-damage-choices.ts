/**
 * The options of the radio groups on SC-16, each with the consequence of
 * choosing it. The groups themselves are drawn by `ChoiceGroup` in
 * SC16-DamageFields.tsx.
 */

import type { DamageOutcome, DamageSeverity } from '../../shared/api/contract'
import { DAMAGE_SEVERITY_LABEL } from './counter-labels'

/** One option of a group. */
export interface ChoiceOption<Value extends string> {
  value: Value
  label: string
  detail: string
}

export const SEVERITY_OPTIONS: readonly ChoiceOption<DamageSeverity>[] = [
  {
    value: 'MINOR',
    label: DAMAGE_SEVERITY_LABEL.MINOR,
    detail: 'Cosmetic or quickly put right. The unit still works and can go out again soon.',
  },
  {
    value: 'MAJOR',
    label: DAMAGE_SEVERITY_LABEL.MAJOR,
    detail: 'Needs workshop time before it can be hired again.',
  },
  {
    value: 'WRITE_OFF',
    label: DAMAGE_SEVERITY_LABEL.WRITE_OFF,
    detail: 'Unsafe or beyond economic repair. The owner decides whether to write it off.',
  },
]

/** The chargeable decision as a radio group carries words and not a flag. */
export type ChargeAnswer = 'charge' | 'absorb'

/** The answer a radio group shows for a decision, which may not be made yet. */
export function chargeAnswerOf(chargeable: boolean | null): ChargeAnswer | null {
  if (chargeable === null) return null
  return chargeable ? 'charge' : 'absorb'
}

/** The two answers to whether the customer is charged, said for a unit that
 *  came back on a hire or for one found outside a hire. */
export function chargeOptions(onHire: boolean): readonly ChoiceOption<ChargeAnswer>[] {
  return [
    {
      value: 'charge',
      label: 'Charge the customer',
      detail: onHire
        ? 'The amount to recover is withheld from the deposit of the hire.'
        : 'Recorded on the report. Damage found outside a hire raises no charge.',
    },
    {
      value: 'absorb',
      label: 'Do not charge the customer',
      detail: 'Fair wear and tear, or our own fault. Toolshed Hire absorbs the repair.',
    },
  ]
}

/** Said beside the chargeable decision (BR-40). */
export const FAIR_WEAR_IS_NOT_CHARGED =
  'Fair wear and tear is not charged. Charge the customer only for damage beyond normal use. Neither answer is chosen for you.'

export const OUTCOME_OPTIONS: readonly ChoiceOption<DamageOutcome>[] = [
  { value: 'RESOLVED', label: 'Repaired', detail: 'The unit was fixed and can go back on the shelf.' },
  { value: 'WRITTEN_OFF', label: 'Written off', detail: 'The unit is not worth repairing and leaves the fleet.' },
]
