/**
 * The branch a member of staff is working at.
 *
 * Every counter screen reads it from here and from nowhere else. Counter staff
 * work at the branch on their account, which comes with the session as
 * `branchCode`, and they cannot change it in the browser. An administrator has
 * no branch on the account, so they choose one, and the choice is kept for the
 * tab in work-branch-storage.ts.
 *
 * The rule is `workBranchFor`, a plain function, so it can be read and tested
 * on its own. `useWorkBranch` hands it to a screen together with the way to
 * choose. The choice lives outside React, the way the basket does, so every
 * screen that reads it sees the same answer at once.
 *
 * This decides what the screens offer and where a booking is made. It keeps
 * nothing safe. The API refuses a write at another branch from counter staff.
 */

import { useSyncExternalStore } from 'react'
import type { SessionUser } from '../../shared/api/contract'
import { logEvent } from '../../shared/api/log'
import { useSession } from '../../shared/use-session'
import { clearStoredWorkBranch, readStoredWorkBranch, writeStoredWorkBranch } from './work-branch-storage'

export interface WorkBranch {
  /** The branch code, or null while an administrator has not chosen one. */
  code: string | null
  /** True for an administrator, who chooses the branch for the tab. */
  chooses: boolean
}

/**
 * The branch a person works at.
 *
 * @param user The signed in account, or null when nobody is signed in.
 * @param chosen What an administrator chose for the tab, or null.
 */
export function workBranchFor(user: SessionUser | null, chosen: string | null): WorkBranch {
  if (user?.role === 'counter') return { code: user.branchCode, chooses: false }
  if (user?.role === 'admin') return { code: chosen, chooses: true }
  return { code: null, chooses: false }
}

type Listener = () => void

const listeners = new Set<Listener>()
let chosenCode: string | null | undefined

function currentChoice(): string | null {
  if (chosenCode === undefined) chosenCode = readStoredWorkBranch()
  return chosenCode
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function announce(next: string | null): void {
  chosenCode = next
  listeners.forEach((listener) => listener())
}

/** Choose the branch an administrator works at, for the rest of the tab. */
export function chooseWorkBranch(code: string): void {
  writeStoredWorkBranch(code)
  logEvent('info', 'counter.branch_chosen', { branch_code: code })
  announce(code)
}

/** Forget the branch an administrator chose, so they are asked again. */
export function forgetWorkBranch(): void {
  clearStoredWorkBranch()
  logEvent('info', 'counter.branch_forgotten', {})
  announce(null)
}

/** Forget what this module remembers, for a test that starts afresh. */
export function resetWorkBranchForTests(): void {
  chosenCode = undefined
  listeners.forEach((listener) => listener())
}

/** The branch the signed in person works at, and the ways to change it. */
export function useWorkBranch(): WorkBranch & {
  choose: (code: string) => void
  forget: () => void
} {
  const { user } = useSession()
  const chosen = useSyncExternalStore(subscribe, currentChoice)
  return { ...workBranchFor(user, chosen), choose: chooseWorkBranch, forget: forgetWorkBranch }
}
