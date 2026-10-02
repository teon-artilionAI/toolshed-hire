/**
 * Reading a fixture branch out of the address bar, for the hire basket.
 *
 * The basket takes its branch from a query string, and a query string is user
 * input. An unrecognised code falls back to a sensible default rather than
 * reaching the fixture availability arithmetic, which throws on an unknown
 * branch by design. The screens on the API do not use this. They pass the
 * code on and let the API judge it.
 */

import type { BranchCode } from '../../shared/types'

export const BRANCH_CODES: BranchCode[] = ['CBD', 'BEL', 'SOM']

/** Where a customer who has not said otherwise is assumed to be. */
export const DEFAULT_BRANCH: BranchCode = 'CBD'

function isBranchCode(value: string | null): value is BranchCode {
  return value !== null && BRANCH_CODES.includes(value as BranchCode)
}

/** A single branch, defaulting to Cape Town CBD. */
export function readBranch(value: string | null): BranchCode {
  return isBranchCode(value) ? value : DEFAULT_BRANCH
}
