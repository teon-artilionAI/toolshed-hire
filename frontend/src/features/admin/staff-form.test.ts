/**
 * Tests for the bodies of the staff account forms on SC-23 and the words the
 * screen uses for an account and a customer's standing.
 *
 * A new account carries exactly the five fields of the route, a branch for
 * counter staff and none for an administrator. A change carries only what
 * changed. A lock is said to hold only until the moment the server gave.
 */

import { describe, expect, it } from 'vitest'
import { OWNER_ACCOUNT, THABO_ACCOUNT } from '../../test/admin-user-samples'
import { ON_HOLD } from '../../test/counter-samples'
import { EMPTY_STAFF_DRAFT, draftOfAccount, newStaffRequestFrom, staffChangesFrom } from './staff-form'
import { lockWords, standingMoveWords, standingMoves } from './staff-words'

describe('the body of a new account', () => {
  it('holds back counter staff with no branch', () => {
    expect(newStaffRequestFrom({ ...EMPTY_STAFF_DRAFT, fullName: 'Lindiwe Dube' }).errors).toEqual({
      branchCode: 'Choose the branch they work at. Counter staff work at one branch.',
    })
  })

  it('carries the five fields, trimmed, with no phone as null', () => {
    const checked = newStaffRequestFrom({
      fullName: '  Lindiwe Dube ',
      email: ' lindiwe@toolshedhire.co.za ',
      phone: '   ',
      role: 'COUNTER_STAFF',
      branchCode: 'SMW',
    })

    expect(checked.body).toEqual({
      email: 'lindiwe@toolshedhire.co.za',
      fullName: 'Lindiwe Dube',
      phone: null,
      role: 'COUNTER_STAFF',
      branchCode: 'SMW',
    })
  })

  it('sends no branch for an administrator, whatever was chosen before', () => {
    const checked = newStaffRequestFrom({ ...EMPTY_STAFF_DRAFT, role: 'ADMIN', branchCode: 'CBD' })

    expect(checked.body?.branchCode).toBeNull()
  })

  it('leaves the name and the address for the server to judge', () => {
    expect(newStaffRequestFrom({ ...EMPTY_STAFF_DRAFT, branchCode: 'CBD' }).errors).toBeNull()
  })
})

describe('the body of a change', () => {
  it('is empty when nothing changed', () => {
    expect(staffChangesFrom(THABO_ACCOUNT, draftOfAccount(THABO_ACCOUNT)).body).toEqual({})
  })

  it('carries only what changed', () => {
    const draft = { ...draftOfAccount(THABO_ACCOUNT), phone: '0825550101', branchCode: 'CBD' }

    expect(staffChangesFrom(THABO_ACCOUNT, draft).body).toEqual({ phone: '0825550101', branchCode: 'CBD' })
  })

  it('asks for a branch when an administrator becomes counter staff', () => {
    const draft = { ...draftOfAccount(OWNER_ACCOUNT), role: 'COUNTER_STAFF' as const }

    expect(staffChangesFrom(OWNER_ACCOUNT, draft).errors?.branchCode).toBeDefined()
  })

  it('takes a phone number off with null', () => {
    const draft = { ...draftOfAccount(OWNER_ACCOUNT), phone: '' }

    expect(staffChangesFrom(OWNER_ACCOUNT, draft).body).toEqual({ phone: null })
  })
})

describe('the words of an account and a standing', () => {
  it('says a lock holds until the moment the server gave, and not after', () => {
    expect(lockWords(THABO_ACCOUNT, new Date('2026-03-12T14:29:00+02:00'))).toMatch(/^Locked until /)
    expect(lockWords(THABO_ACCOUNT, new Date('2026-03-12T14:30:00+02:00'))).toBe('Not locked')
    expect(lockWords(OWNER_ACCOUNT)).toBe('Not locked')
  })

  it('offers the two standings a customer is not in', () => {
    expect(standingMoves(ON_HOLD)).toEqual(['ACTIVE', 'BLACKLISTED'])
  })

  it('says a released hold keeps the server count of bookings not collected', () => {
    expect(standingMoveWords(ON_HOLD, 'ACTIVE').consequence).toContain('stays at 3')
  })
})
