/**
 * The sample branch that stands in for the branch a person works at.
 *
 * The dashboard and the diary are not connected to the API yet. They list
 * sample bookings, and those are kept against sample branches. The branch a
 * person works at is real, and comes from work-branch.ts like it does on every
 * counter screen. This maps one onto the other, so counter staff see the
 * sample bookings of their own branch.
 *
 * The sample data was written before the API, and it names two branches
 * differently. That is why the mapping is a table and not an equality.
 *
 * An administrator who has not chosen a branch yet starts at the first sample
 * branch, and can look at another one on any screen that offers a branch
 * filter. That filter belongs to the screen. Nothing a screen does here
 * changes the branch the person works at.
 *
 * This file goes when the dashboard and the diary read from the API.
 */

import { branches } from '../../shared/fixtures'
import type { Branch, BranchCode } from '../../shared/types'
import { useWorkBranch } from './work-branch'

/** The sample branch code for each branch code the API uses. */
const SAMPLE_CODE_FOR: Record<string, BranchCode> = {
  CBD: 'CBD',
  BLV: 'BEL',
  SMW: 'SOM',
}

/** The sample branch for the branch the person works at, or the first sample
 *  branch when there is none yet or it names one the sample data does not have. */
export function useHomeBranch(): Branch {
  const { code } = useWorkBranch()
  const sampleCode = code ? SAMPLE_CODE_FOR[code] : undefined
  return branches.find((branch) => branch.code === sampleCode) ?? branches[0]
}
