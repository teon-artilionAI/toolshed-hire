/**
 * The small vocabulary the SC-14 checkout wizard works in.
 *
 * The accessory checklist lives here rather than in the shared fixtures on
 * purpose. There is no accessory entity in the domain model, and adding one
 * to the fixtures would put a type in the data that the ERD does not
 * describe. What a counter assistant hands over with a breaker is a counter
 * procedure, so it sits with the counter screens.
 */

import type { ConditionGrade } from '../../shared/types'

export type DepositMethod = 'CARD_HOLD' | 'CASH' | 'EFT'

export interface ItemDraft {
  tagConfirmed: boolean
  conditionOut: ConditionGrade
  meter: string
  note: string
}

/** One physical unit going out on this hire, flattened for display. */
export interface CheckoutRow {
  itemId: string
  tag: string
  modelName: string
  manufacturer: string
  categoryId: string
  hasMeter: boolean
  meterOnFile?: number
  conditionOnFile: ConditionGrade
}

export const CONDITION_GRADES: ConditionGrade[] = ['A', 'B', 'C', 'D']

export const CONDITION_LABEL: Record<ConditionGrade, string> = {
  A: 'A, as new',
  B: 'B, good working order',
  C: 'C, worn but serviceable',
  D: 'D, damaged, do not release',
}

const ACCESSORIES_BY_CATEGORY: Record<string, string[]> = {
  'cat-1': ['SDS-plus bit and chisel set', 'Side handle and depth stop', 'Carry case'],
  'cat-2': ['Wheel kit', 'Fuel can, filled', 'Watering can for asphalt work'],
  'cat-3': ['Drum stand and tow pin', 'Paddle spanner', 'Mixing scoop'],
  'cat-4': ['Cutting wheel fitted and checked', 'Blade spanner', 'Water bottle and hose'],
  'cat-5': ['Guardrails and toe boards', 'Stabiliser legs', 'Assembly instructions'],
  'cat-6': ['Grass blade and nylon head', 'Harness', 'Visor and gloves'],
  'cat-7': ['Fuel can, filled', 'Extension lead, 20 m', 'Earth spike'],
}

const ALWAYS_HANDED_OVER = 'Operating manual and safety sheet'

/** Everything that should go over the counter with this set of units. */
export function accessoriesFor(categoryIds: string[]): string[] {
  const list = new Set<string>([ALWAYS_HANDED_OVER])
  for (const id of categoryIds) {
    for (const item of ACCESSORIES_BY_CATEGORY[id] ?? []) list.add(item)
  }
  return [...list]
}
