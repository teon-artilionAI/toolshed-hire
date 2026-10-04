/**
 * The branches as SC-23 names and offers them.
 *
 * A staff account carries the code of its branch and not its name, so the
 * screen names each branch from the API's own list, which is catalogue data
 * and fresh for a minute. A code the list does not hold, or every code while
 * the list cannot be read, is shown as the code itself, so a row never goes
 * blank. A branch an account already holds stays in the menu the same way.
 */

import { useQuery } from '@tanstack/react-query'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import { queryPhase } from '../../shared/api/query-phase'

export interface BranchOption {
  value: string
  label: string
}

export interface BranchList {
  /** Every branch the API lists, by its name. */
  options: BranchOption[]
  /** The name of a branch, or its code when the list does not hold it. */
  nameOf: (code: string) => string
  /** True when the list could not be read. */
  failed: boolean
}

export function useBranchList(): BranchList {
  const branches = useQuery(catalogueQueries.branches())
  const options = (branches.data?.items ?? []).map((branch) => ({ value: branch.code, label: branch.name }))
  return {
    options,
    nameOf: (code) => options.find((option) => option.value === code)?.label ?? code,
    failed: queryPhase(branches) === 'failed',
  }
}

/** The menu of branches with a first choice, and a branch already held kept in it. */
export function branchMenu(list: BranchList, first: BranchOption, held: string): BranchOption[] {
  const known = held === '' || list.options.some((option) => option.value === held)
  return [first, ...list.options, ...(known ? [] : [{ value: held, label: held }])]
}
