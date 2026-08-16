/** The shapes the SC-15 return inspection works in. */

import type { ConditionGrade } from '../../shared/types'
import { CONDITION_GRADES } from './SC14-checkout-model'

/** One unit on the hire, flattened for the inspection. */
export interface ReturnRow {
  itemId: string
  assetId: string
  tag: string
  modelName: string
  manufacturer: string
  lateFeePerDay: number
  conditionOut: ConditionGrade
  meterOut?: number
  hasMeter: boolean
  returnedAt?: string
  conditionIn?: ConditionGrade
}

/** What the assistant is entering for a unit that is coming back now. */
export interface ReturnDraft {
  received: boolean
  conditionIn: ConditionGrade
  meterIn: string
  chargeDamage: boolean
  damageCharge: string
}

/** A is the best grade, so a later letter is a worse unit. */
export function isWorse(now: ConditionGrade, before: ConditionGrade): boolean {
  return CONDITION_GRADES.indexOf(now) > CONDITION_GRADES.indexOf(before)
}
