/**
 * Reading a branch out of the address bar.
 *
 * Every customer screen takes its branch from a query string, and a query
 * string is user input. An unrecognised code falls back to a sensible
 * default rather than reaching the availability engine, which throws on an
 * unknown branch by design.
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

/** A branch filter, where "no branch" means every branch. */
export function readBranchFilter(value: string | null): BranchCode | 'ALL' {
  return isBranchCode(value) ? value : 'ALL'
}
