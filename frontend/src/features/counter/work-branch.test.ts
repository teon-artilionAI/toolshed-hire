/**
 * Tests for the branch a member of staff works at.
 *
 * Counter staff work at the branch on their account and cannot change it. An
 * administrator has none, chooses one, and the choice is kept for the tab
 * under one key and nothing else. A customer, or nobody, works at no branch.
 */

import { describe, expect, it } from 'vitest'
import { ADMIN, COUNTER_STAFF, CUSTOMER } from '../../test/session-samples'
import {
  chooseWorkBranch,
  forgetWorkBranch,
  resetWorkBranchForTests,
  workBranchFor,
} from './work-branch'
import { WORK_BRANCH_STORAGE_KEY, readStoredWorkBranch } from './work-branch-storage'

describe('the branch a person works at', () => {
  it('is the branch on the account for counter staff, whatever was chosen in the tab', () => {
    expect(workBranchFor(COUNTER_STAFF, null)).toEqual({ code: 'BLV', chooses: false })
    expect(workBranchFor(COUNTER_STAFF, 'SMW')).toEqual({ code: 'BLV', chooses: false })
  })

  it('is nothing for counter staff whose account names no branch', () => {
    expect(workBranchFor({ ...COUNTER_STAFF, branchCode: null }, 'CBD')).toEqual({ code: null, chooses: false })
  })

  it('is what an administrator chose, and nothing until they choose', () => {
    expect(workBranchFor(ADMIN, null)).toEqual({ code: null, chooses: true })
    expect(workBranchFor(ADMIN, 'SMW')).toEqual({ code: 'SMW', chooses: true })
  })

  it('is nothing for a customer or for nobody', () => {
    expect(workBranchFor(CUSTOMER, 'CBD')).toEqual({ code: null, chooses: false })
    expect(workBranchFor(null, 'CBD')).toEqual({ code: null, chooses: false })
  })
})

describe('the choice an administrator makes', () => {
  it('is kept for the tab under its one key, and read back after a reload', () => {
    chooseWorkBranch('SMW')

    expect(Object.keys(window.sessionStorage)).toEqual([WORK_BRANCH_STORAGE_KEY])
    expect(window.sessionStorage.getItem(WORK_BRANCH_STORAGE_KEY)).toBe('SMW')
    expect(window.localStorage.getItem(WORK_BRANCH_STORAGE_KEY)).toBeNull()

    // A reload starts the module afresh, and the choice comes back from the tab.
    resetWorkBranchForTests()
    expect(readStoredWorkBranch()).toBe('SMW')
  })

  it('is gone once forgotten', () => {
    chooseWorkBranch('CBD')

    forgetWorkBranch()

    expect(window.sessionStorage.getItem(WORK_BRANCH_STORAGE_KEY)).toBeNull()
    expect(readStoredWorkBranch()).toBeNull()
  })

  it('is not believed when the tab holds something that is not a branch code', () => {
    window.sessionStorage.setItem(WORK_BRANCH_STORAGE_KEY, '<script>')

    expect(readStoredWorkBranch()).toBeNull()
  })
})
