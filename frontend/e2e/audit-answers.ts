/**
 * The API answered by the spec itself, for the audit trail and the
 * notification log on SC-24.
 *
 * The accessibility scan and the narrow screen check of SC-24 need a signed in
 * owner, events of every kind and emails that went out and failed. They answer
 * beside the dashboard and the report in admin-answers.ts, with long names,
 * long addresses and long errors, which are what break a layout. The fields
 * that changed include a list and a record inside a record, so the words they
 * are written in are scanned too. A side the server kept nothing of is an
 * empty object, the way the real API sends it.
 */

import { dateFromToday } from './hire-dates.ts'

const TODAY = dateFromToday(0)
const YESTERDAY = dateFromToday(-1)

function event(id: number, overrides: Record<string, unknown>) {
  return {
    id,
    occurredAt: `${TODAY}T08:0${id % 10}:00+02:00`,
    actorUserId: '0b0f6f3e-1111-4a2b-9c3d-000000000005',
    actorName: 'Marius Pretorius-Vanderwesthuizen',
    actorRole: 'ADMIN',
    entityType: 'reservation',
    entityId: '5f0c2a9e-0000-4000-8000-000000000124',
    action: 'reservation.confirmed',
    beforeState: { status: 'HELD', holdExpiresAt: `${TODAY}T08:30:00+02:00` },
    afterState: { status: 'CONFIRMED', holdExpiresAt: null, assetTags: ['TSH-PC-0007', 'TSH-PC-0011', 'TSH-BR-0003'] },
    requestId: '6a0b1c2d-0000-4000-8000-000000000001',
    ...overrides,
  }
}

const AUDIT_PAGE = {
  items: [
    event(3, {}),
    event(2, {
      actorUserId: null,
      actorName: null,
      actorRole: null,
      entityType: 'rental',
      entityId: '9c3b1f2a-0000-4000-8000-000000000099',
      action: 'rental.overdue',
      beforeState: { status: 'OPEN' },
      afterState: { status: 'OVERDUE', deposit: { held: '4500.00', withheld: '0.00', waitingOn: 'ITEMS_OUT' } },
      requestId: null,
    }),
    event(1, {
      actorName: 'Elmarie Fourie-Vanderwesthuizen',
      entityType: 'charge',
      entityId: 'c3300000-0000-4000-8000-000000000011',
      action: 'charge.adjusted',
      beforeState: {},
      afterState: {
        status: 'PENDING',
        reason: 'Charged twice for the same day because the booking was entered at two counters at once',
        rental_reference: 'TSH-H-26-000099',
        charge_type: 'ADJUSTMENT',
        amount_inc_vat: '-1150.00',
        rental_status: 'RETURNED',
        balance_due: '0.00',
      },
    }),
  ],
  page: 1,
  pageSize: 20,
  total: 46,
}

function email(number: number, overrides: Record<string, unknown>) {
  return {
    id: `e5500000-0000-4000-8000-00000000000${number}`,
    reservationId: '5f0c2a9e-0000-4000-8000-000000000124',
    reservationReference: 'TSH-R-26-000124',
    type: 'BOOKING_CONFIRMATION',
    recipientEmail: 'wesley.bartholomew.adonis@buildright-construction.co.za',
    subject: 'Your Toolshed Hire booking TSH-R-26-000124 is confirmed for collection at Cape Town CBD',
    status: 'SENT',
    attempts: 1,
    lastError: null,
    queuedAt: `${YESTERDAY}T15:30:00+02:00`,
    sentAt: `${YESTERDAY}T15:30:04+02:00`,
    resendOf: null,
    ...overrides,
  }
}

const NOTIFICATION_PAGE = {
  items: [
    email(3, { status: 'QUEUED', attempts: 0, sentAt: null, queuedAt: `${TODAY}T08:01:00+02:00`, resendOf: 'e5500000-0000-4000-8000-000000000002' }),
    email(2, {
      status: 'FAILED',
      sentAt: null,
      lastError:
        'The receiving server said 552 5.2.2 the mailbox wesley.bartholomew.adonis@buildright-construction.co.za is full and accepts no more mail.',
    }),
    email(1, { reservationReference: 'TSH-R-26-000123' }),
  ],
  page: 1,
  pageSize: 20,
  total: 31,
}

/** What the two routes of SC-24 answer. */
export const AUDIT_ANSWERS: Record<string, unknown> = {
  'GET /api/admin/audit-events': AUDIT_PAGE,
  'GET /api/admin/notifications': NOTIFICATION_PAGE,
}
