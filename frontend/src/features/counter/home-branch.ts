/**
 * The sample branch that stands in for the branch on the signed in account.
 *
 * The counter screens are not connected to the API yet. They list sample
 * bookings, and those are kept against sample branches. The account is real
 * and carries the code of the branch the person works at. This maps one onto
 * the other, so counter staff see the sample bookings of their own branch.
 *
 * The sample data was written before the API, and it names two branches
 * differently. That is why the mapping is a table and not an equality.
 *
 * An admin has no branch on the account. They start at the first branch and
 * can look at another one on any screen that offers a branch filter. That
 * filter belongs to the screen. Nothing a screen does changes the branch on
 * the account.
 *
 * This file goes when the counter screens read their branch from the API.
 */

import { branches } from '../../shared/fixtures'
import type { Branch, BranchCode } from '../../shared/types'
import { useSession } from '../../shared/use-session'

/** The sample branch code for each branch code the API uses. */
const SAMPLE_CODE_FOR: Record<string, BranchCode> = {
  CBD: 'CBD',
  BLV: 'BEL',
  SMW: 'SOM',
}

/** The sample branch for the signed in account, or the first sample branch
 *  when the account has none or names one the sample data does not have. */
export function useHomeBranch(): Branch {
  const { user } = useSession()
  const sampleCode = user?.branchCode ? SAMPLE_CODE_FOR[user.branchCode] : undefined
  return branches.find((branch) => branch.code === sampleCode) ?? branches[0]
}
