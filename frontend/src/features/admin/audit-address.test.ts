/**
 * Tests for reading SC-24 from the address and writing it back.
 */

import { describe, expect, it } from 'vitest'
import {
  NO_TRAIL_FILTERS,
  isRecordKey,
  notificationQueryFor,
  readNotificationFilters,
  readTrailFilters,
  readView,
  trailIsFiltered,
  trailQueryFor,
  viewHref,
  writeNotificationFilters,
  writeTrailFilters,
} from './audit-address'

describe('the view', () => {
  it('is the trail unless the address names the notification log', () => {
    expect(readView(new URLSearchParams(''))).toBe('trail')
    expect(readView(new URLSearchParams('view=elsewhere'))).toBe('trail')
    expect(readView(new URLSearchParams('view=notifications'))).toBe('notifications')
  })

  it('is linked from its first page with no filter', () => {
    expect(viewHref('/admin/audit', 'trail')).toBe('/admin/audit')
    expect(viewHref('/admin/audit', 'notifications')).toBe('/admin/audit?view=notifications')
  })
})

describe('the filters of the trail', () => {
  it('read every filter by the name the API takes, and leave out what is empty', () => {
    const read = readTrailFilters(
      new URLSearchParams(
        'entityType=reservation&entityId=%205f0c2a9e-0000-4000-8000-000000000124%20&action=&actorUserId=abc&from=2026-03-01&to=2026-03-12&page=3',
      ),
    )

    expect(read).toEqual({
      entityType: 'reservation',
      entityId: '5f0c2a9e-0000-4000-8000-000000000124',
      action: null,
      actorUserId: 'abc',
      from: '2026-03-01',
      to: '2026-03-12',
      page: 3,
    })
  })

  it('drop a day that is not on the calendar and a page that is not a page', () => {
    const read = readTrailFilters(new URLSearchParams('from=2026-02-31&to=soon&page=-2'))

    expect(read).toEqual(NO_TRAIL_FILTERS)
  })

  it('write back what they read, with the first page left out', () => {
    const address = 'entityType=rental&action=rental.overdue&from=2026-03-01&page=2'
    const read = readTrailFilters(new URLSearchParams(address))

    expect(writeTrailFilters(read).toString()).toBe(address)
    expect(writeTrailFilters({ ...read, page: 1 }).toString()).toBe('entityType=rental&action=rental.overdue&from=2026-03-01')
  })

  it('say whether any filter is applied, the page aside', () => {
    expect(trailIsFiltered({ ...NO_TRAIL_FILTERS, page: 4 })).toBe(false)
    expect(trailIsFiltered({ ...NO_TRAIL_FILTERS, actorUserId: 'abc' })).toBe(true)
  })

  it('tell the key of a record from a reference, which the server does not take', () => {
    expect(isRecordKey('5f0c2a9e-0000-4000-8000-000000000124')).toBe(true)
    expect(isRecordKey('5F0C2A9E-0000-4000-8000-000000000124')).toBe(true)
    expect(isRecordKey('TSH-R-26-000124')).toBe(false)
    expect(isRecordKey('5f0c2a9e00004000800000000000124')).toBe(false)
  })

  it('make the query with twenty to a page', () => {
    expect(trailQueryFor({ ...NO_TRAIL_FILTERS, entityType: 'charge' })).toEqual({
      entityType: 'charge',
      entityId: undefined,
      action: undefined,
      actorUserId: undefined,
      from: undefined,
      to: undefined,
      page: 1,
      pageSize: 20,
    })
  })
})

describe('the filter of the notification log', () => {
  it('reads a status the log has and drops any other', () => {
    expect(readNotificationFilters(new URLSearchParams('view=notifications&status=FAILED&page=2'))).toEqual({
      status: 'FAILED',
      page: 2,
    })
    expect(readNotificationFilters(new URLSearchParams('status=LOST')).status).toBeNull()
  })

  it('always names its view when written', () => {
    expect(writeNotificationFilters({ status: null, page: 1 }).toString()).toBe('view=notifications')
    expect(writeNotificationFilters({ status: 'SENT', page: 2 }).toString()).toBe('view=notifications&status=SENT&page=2')
  })

  it('makes the query with twenty to a page', () => {
    expect(notificationQueryFor({ status: 'QUEUED', page: 1 })).toEqual({ status: 'QUEUED', page: 1, pageSize: 20 })
  })
})
