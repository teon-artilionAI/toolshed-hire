/**
 * The condition grades of the sample data the return screen still reads.
 *
 * SC-14 reads from the API now, and the grades it offers are the three the API
 * has, in counter-labels.ts. SC-15 still shows sample hires, and those carry a
 * fourth grade for a damaged unit, so it keeps the four here until it is
 * connected. The words for the first three are the same ones, taken from
 * counter-labels.ts, so the two screens never describe a grade differently.
 */

import type { ConditionGrade } from '../../shared/types'
import { CONDITION_GRADE_LABEL } from './counter-labels'

export const CONDITION_GRADES: ConditionGrade[] = ['A', 'B', 'C', 'D']

export const CONDITION_LABEL: Record<ConditionGrade, string> = {
  ...CONDITION_GRADE_LABEL,
  D: 'D, damaged, do not release',
}
