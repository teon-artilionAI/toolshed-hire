/**
 * Tests for the words SC-24 writes the trail in.
 */

import { describe, expect, it } from 'vitest'
import { actionWords, actorWords, changeWords, changedFields, entityTypeWords, fieldWords, valueWords } from './audit-words'

describe('names written as words', () => {
  it('reads a known action by hand and any other from its name', () => {
    expect(actionWords('auth.login_succeeded')).toBe('Signed in')
    expect(actionWords('reservation.confirmed')).toBe('Reservation confirmed')
    expect(actionWords('damage_report.sent_for_repair')).toBe('Damage report sent for repair')
    expect(actionWords('charge.reversed')).toBe('Charge reversed')
  })

  it('reads a kind of record and a field', () => {
    expect(entityTypeWords('reservation')).toBe('Booking')
    expect(entityTypeWords('purchase_order')).toBe('Purchase order')
    expect(fieldWords('holdExpiresAt')).toBe('Hold expires at')
    expect(fieldWords('deposit_held')).toBe('Deposit held')
  })

  it('says who acted and in what role, or that the system did', () => {
    expect(actorWords({ actorName: 'Marius Pretorius', actorRole: 'ADMIN' })).toBe('Marius Pretorius, administrator')
    expect(actorWords({ actorName: 'Thabo Ncube', actorRole: 'COUNTER_STAFF' })).toBe('Thabo Ncube, counter staff')
    expect(actorWords({ actorName: null, actorRole: null })).toBe('the system, with no person behind it')
  })
})

describe('values written as words', () => {
  it('writes every kind of value without raw JSON', () => {
    expect(valueWords(null)).toBe('nothing')
    expect(valueWords(true)).toBe('yes')
    expect(valueWords(false)).toBe('no')
    expect(valueWords(3)).toBe('3')
    expect(valueWords('')).toBe('empty')
    expect(valueWords([])).toBe('none')
    expect(valueWords(['TSH-PC-0007', 'TSH-PC-0011'])).toBe('TSH-PC-0007, TSH-PC-0011')
    expect(valueWords({ held: '5555.55', nested: { gradeOut: 'B' } })).toBe('held 5555.55; nested grade out B')
  })

  it('writes an instant at the branches and a word of the backend in lower case, and keeps a short code', () => {
    expect(valueWords('2026-03-12T08:15:00+02:00')).toBe('12 Mar 2026 at 08:15')
    expect(valueWords('CONFIRMED')).toBe('confirmed')
    expect(valueWords('ITEMS_OUT')).toBe('items out')
    expect(valueWords('CBD')).toBe('CBD')
    expect(valueWords('TSH-PC-0007')).toBe('TSH-PC-0007')
    expect(valueWords('2026-03-12')).toBe('2026-03-12')
  })
})

describe('the fields that changed', () => {
  it('lists each field that changed with how it read before and after, and leaves out one that did not', () => {
    const changes = changedFields(
      { status: 'HELD', branchCode: 'BLV', reason: 'Late' },
      { status: 'CONFIRMED', branchCode: 'BLV', confirmedAt: '2026-03-12T08:05:00+02:00' },
    )

    expect(changes).toEqual([
      { field: 'Status', before: 'held', after: 'confirmed' },
      { field: 'Confirmed at', before: null, after: '12 Mar 2026 at 08:05' },
      { field: 'Reason', before: 'Late', after: null },
    ])
    expect(changes.map(changeWords)).toEqual([
      'Was held. Now confirmed.',
      'Set to 12 Mar 2026 at 08:05.',
      'Was Late. No longer recorded.',
    ])
  })

  it('reads a record made from nothing, and a change with nothing kept', () => {
    expect(changedFields(null, { status: 'DRAFT' })).toEqual([{ field: 'Status', before: null, after: 'draft' }])
    expect(changedFields(null, null)).toEqual([])
  })
})
