/**
 * The audit trail and the notification log, for the owner.
 *
 * Three routes. Two read a page each, newest first, and the third sends a
 * failed booking confirmation again. Each function makes one call and reads
 * the body into its contract type, checking every member, so a body that
 * breaks the contract fails here with the name of the field.
 *
 * The trail is read only. There is no route that changes an event, and the
 * database role the API runs as cannot change one either, so nothing here
 * offers to. A re-send never changes the failed email. It writes a new one,
 * so the failure and the second attempt are both in the log.
 */

import { malformedResponse } from '../api-problem'
import { api } from './client'
import type {
  AuditActorRole,
  AuditEvent,
  AuditEventPage,
  AuditEventQuery,
  AuditState,
  EmailNotification,
  EmailNotificationPage,
  EmailNotificationQuery,
  NotificationStatus,
  NotificationType,
} from './contract'
import {
  readCount,
  readList,
  readNullableOneOf,
  readNullableText,
  readNullableTimestamp,
  readObject,
  readOneOf,
  readText,
} from './read'

const AUDIT_ENDPOINT = '/admin/audit-events'
const NOTIFICATIONS_ENDPOINT = '/admin/notifications'

/** How many events or emails a page of the log holds. */
export const LOG_PAGE_SIZE = 20

/** Every role an event can name, as the backend stores it. */
export const AUDIT_ACTOR_ROLES: readonly AuditActorRole[] = ['CUSTOMER', 'COUNTER_STAFF', 'ADMIN']

/** Every status an email can be in, in the order the filter lists them. */
export const NOTIFICATION_STATUSES: readonly NotificationStatus[] = ['FAILED', 'QUEUED', 'SENT']

const NOTIFICATION_TYPES: readonly NotificationType[] = ['BOOKING_CONFIRMATION']

/** An instant the contract never sends as null. */
function readInstant(record: Record<string, unknown>, key: string, path: string): string {
  const value = readNullableTimestamp(record, key, path)
  if (value === null) throw malformedResponse(path, `Expected field ${key} from ${path} to be an instant, got null.`)
  return value
}

/** The fields before or after a change. An object, or null when there were none. */
function readState(record: Record<string, unknown>, key: string, path: string): AuditState | null {
  const value = record[key]
  if (value === null) return null
  return readObject(value, path, `the field ${key} of an audit event, as an object or null`)
}

function readAuditEvent(value: unknown, path: string): AuditEvent {
  const record = readObject(value, path, 'an audit event')
  return {
    id: readCount(record, 'id', path),
    occurredAt: readInstant(record, 'occurredAt', path),
    actorUserId: readNullableText(record, 'actorUserId', path),
    actorName: readNullableText(record, 'actorName', path),
    actorRole: readNullableOneOf(record, 'actorRole', path, AUDIT_ACTOR_ROLES),
    entityType: readText(record, 'entityType', path),
    entityId: readText(record, 'entityId', path),
    action: readText(record, 'action', path),
    beforeState: readState(record, 'beforeState', path),
    afterState: readState(record, 'afterState', path),
    requestId: readNullableText(record, 'requestId', path),
  }
}

function readNotification(value: unknown, path: string): EmailNotification {
  const record = readObject(value, path, 'a notification')
  return {
    id: readText(record, 'id', path),
    reservationId: readText(record, 'reservationId', path),
    reservationReference: readText(record, 'reservationReference', path),
    type: readOneOf(record, 'type', path, NOTIFICATION_TYPES),
    recipientEmail: readText(record, 'recipientEmail', path),
    subject: readText(record, 'subject', path),
    status: readOneOf(record, 'status', path, NOTIFICATION_STATUSES),
    attempts: readCount(record, 'attempts', path),
    lastError: readNullableText(record, 'lastError', path),
    queuedAt: readInstant(record, 'queuedAt', path),
    sentAt: readNullableTimestamp(record, 'sentAt', path),
    resendOf: readNullableText(record, 'resendOf', path),
  }
}

function readPageMembers(record: Record<string, unknown>, path: string) {
  return {
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

function readAuditPage(value: unknown, path: string): AuditEventPage {
  const record = readObject(value, path, 'a page of the audit trail')
  return { items: readList(record, 'items', path, readAuditEvent), ...readPageMembers(record, path) }
}

function readNotificationPage(value: unknown, path: string): EmailNotificationPage {
  const record = readObject(value, path, 'a page of the notification log')
  return { items: readList(record, 'items', path, readNotification), ...readPageMembers(record, path) }
}

/**
 * GET /api/admin/audit-events. One page of the trail, newest first.
 *
 * @throws ApiError with status 422 naming the field when a filter is refused,
 *   and 403 for anyone but an administrator.
 */
export function listAuditEvents(query: AuditEventQuery, signal?: AbortSignal): Promise<AuditEventPage> {
  return api.get(AUDIT_ENDPOINT, readAuditPage, { query, signal })
}

/**
 * GET /api/admin/notifications. One page of the emails, newest first.
 *
 * @throws ApiError with status 422 when the status is refused, and 403 for
 *   anyone but an administrator.
 */
export function listNotifications(
  query: EmailNotificationQuery,
  signal?: AbortSignal,
): Promise<EmailNotificationPage> {
  return api.get(NOTIFICATIONS_ENDPOINT, readNotificationPage, { query, signal })
}

/**
 * POST /api/admin/notifications/{id}/resend. No body. Answers 201 with the new
 * email, which the server sends after its commit.
 *
 * @throws ApiError with status 409 when the email did not fail, and 403 for
 *   anyone but an administrator.
 */
export function resendNotification(id: string): Promise<EmailNotification> {
  return api.post(`${NOTIFICATIONS_ENDPOINT}/${encodeURIComponent(id)}/resend`, undefined, readNotification)
}
