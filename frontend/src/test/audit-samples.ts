/**
 * The audit trail and the notification log for tests, shaped the way the
 * contract for the admin operations describes them.
 *
 * The owner is `ADMIN` from session-samples.ts. The clock of the tests that use
 * these is pinned to `TEST_NOW`, the morning of 12 March 2026 at the branches.
 */

import type { AuditEvent, AuditEventPage, EmailNotification, EmailNotificationPage } from '../shared/api/contract'
import { RESERVATION_ID } from './reservation-samples'
import { ADMIN } from './session-samples'

export const AUDIT_ROUTE = 'GET /api/admin/audit-events'
export const NOTIFICATIONS_ROUTE = 'GET /api/admin/notifications'

export function resendRoute(id: string): string {
  return `POST /api/admin/notifications/${id}/resend`
}

/** The booking the owner confirmed, with the fields that changed. */
export const CONFIRMED_EVENT: AuditEvent = {
  id: 1234,
  occurredAt: '2026-03-12T07:45:00+02:00',
  actorUserId: ADMIN.id,
  actorName: ADMIN.fullName,
  actorRole: 'ADMIN',
  entityType: 'reservation',
  entityId: RESERVATION_ID,
  action: 'reservation.confirmed',
  beforeState: { status: 'HELD', holdExpiresAt: '2026-03-12T08:15:00+02:00' },
  afterState: { status: 'CONFIRMED', holdExpiresAt: null, assetTags: ['TSH-PC-0007', 'TSH-PC-0011'] },
  requestId: '6a0b1c2d-0000-4000-8000-000000000001',
}

/** A hire the lazy sweep moved to overdue, with no person behind it. */
export const SWEEP_EVENT: AuditEvent = {
  id: 1233,
  occurredAt: '2026-03-12T06:00:00+02:00',
  actorUserId: null,
  actorName: null,
  actorRole: null,
  entityType: 'rental',
  entityId: '9c3b1f2a-0000-4000-8000-000000000099',
  action: 'rental.overdue',
  beforeState: { status: 'OPEN' },
  afterState: { status: 'OVERDUE', deposit: { held: '5555.55', withheld: '0.00' } },
  requestId: null,
}

/** One page of the trail, the way `GET /api/admin/audit-events` answers. */
export function auditPage(items: AuditEvent[], overrides: Partial<AuditEventPage> = {}): AuditEventPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}

/** A confirmation the mail provider refused. */
export const FAILED_EMAIL: EmailNotification = {
  id: 'e5500000-0000-4000-8000-000000000001',
  reservationId: RESERVATION_ID,
  reservationReference: 'TSH-R-26-000124',
  type: 'BOOKING_CONFIRMATION',
  recipientEmail: 'w.adonis@buildright.co.za',
  subject: 'Your Toolshed Hire booking TSH-R-26-000124 is confirmed',
  status: 'FAILED',
  attempts: 1,
  lastError: 'The mailbox w.adonis@buildright.co.za is full.',
  queuedAt: '2026-03-11T15:30:00+02:00',
  sentAt: null,
  resendOf: null,
}

/** A confirmation that went out. */
export const SENT_EMAIL: EmailNotification = {
  ...FAILED_EMAIL,
  id: 'e5500000-0000-4000-8000-000000000002',
  reservationReference: 'TSH-R-26-000125',
  recipientEmail: 'thandi@example.co.za',
  subject: 'Your Toolshed Hire booking TSH-R-26-000125 is confirmed',
  status: 'SENT',
  lastError: null,
  queuedAt: '2026-03-11T16:00:00+02:00',
  sentAt: '2026-03-11T16:02:00+02:00',
}

/** The new email a re-send of the failed one answers with. */
export const RESENT_EMAIL: EmailNotification = {
  ...FAILED_EMAIL,
  id: 'e5500000-0000-4000-8000-000000000003',
  status: 'QUEUED',
  attempts: 0,
  lastError: null,
  queuedAt: '2026-03-12T08:01:00+02:00',
  resendOf: FAILED_EMAIL.id,
}

/** One page of the log, the way `GET /api/admin/notifications` answers. */
export function emailPage(
  items: EmailNotification[],
  overrides: Partial<EmailNotificationPage> = {},
): EmailNotificationPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}
