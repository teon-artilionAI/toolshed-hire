/**
 * Where an administrator's choice of branch is kept for the tab.
 *
 * An administrator has no branch on their account and chooses one to work the
 * counter at. The choice is one branch code under one fixed key in
 * `sessionStorage`, so a reload keeps it and closing the tab ends it. It holds
 * no name and no token. Counter staff never write here, because their branch
 * comes from their account.
 *
 * A browser can refuse web storage altogether. That is logged and never
 * thrown, because the choice still works in memory without it. It then lasts
 * until the next reload.
 */

import { logEvent } from '../../shared/api/log'

/** The one key the choice is kept under. */
export const WORK_BRANCH_STORAGE_KEY = 'toolshed.counter-branch'

/** A branch code as the API writes one. Anything else in storage was put
 *  there by hand and is not believed. */
const BRANCH_CODE_PATTERN = /^[A-Z]{2,8}$/

function context(operation: string, cause: unknown): Record<string, unknown> {
  return {
    operation,
    key: WORK_BRANCH_STORAGE_KEY,
    reason: cause instanceof Error ? `${cause.name} ${cause.message}` : String(cause),
  }
}

/** The branch code kept for the tab, or null when none is or it cannot be read. */
export function readStoredWorkBranch(): string | null {
  try {
    const stored = window.sessionStorage.getItem(WORK_BRANCH_STORAGE_KEY)
    return stored !== null && BRANCH_CODE_PATTERN.test(stored) ? stored : null
  } catch (cause) {
    logEvent('warn', 'counter.branch_storage_unreadable', context('read', cause))
    return null
  }
}

/** Keep the chosen branch code for the tab. */
export function writeStoredWorkBranch(code: string): void {
  try {
    window.sessionStorage.setItem(WORK_BRANCH_STORAGE_KEY, code)
  } catch (cause) {
    logEvent('warn', 'counter.branch_storage_not_kept', context('write', cause))
  }
}

/** Forget the chosen branch, so the administrator is asked again. */
export function clearStoredWorkBranch(): void {
  try {
    window.sessionStorage.removeItem(WORK_BRANCH_STORAGE_KEY)
  } catch (cause) {
    logEvent('warn', 'counter.branch_storage_not_cleared', context('remove', cause))
  }
}
