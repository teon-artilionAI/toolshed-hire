/**
 * The admin operations wire types. The audit trail, the notification log and
 * its re-send, the corrections of a charge, the release of a unit and the
 * reallocation that follows it.
 *
 * These are written by hand from the contract for branch 018, because the
 * backend half of the change is built at the same time and the OpenAPI
 * document does not describe these routes yet. Once it does, `npm run
 * api:types` brings them into schema.d.ts and each type here is rebuilt from
 * the generated shapes, the way every other contract module is. Until then a
 * reader checks every member of every body, so a body that breaks the contract
 * still fails at the boundary with the name of the field.
 *
 * Two members are added to types that are already generated. A charge on a
 * hire gains `reversesChargeId` and `reason`, and the checkout preview gains
 * `unitsShort`. contract-counter.ts adds them to its own types from the two
 * shapes at the bottom of this file.
 *
 * Nothing imports this file but contract.ts and contract-counter.ts. The
 * application imports these types from contract.ts, like every other wire type.
 */

import type { IsoDate, IsoTimestamp, Money } from './contract-kit'

/** The role an audit event copies from the account that acted, as the backend
 *  stores it. It is copied so the trail survives a later change of role. */
export type AuditActorRole = 'CUSTOMER' | 'COUNTER_STAFF' | 'ADMIN'

/**
 * The fields of a record before or after a change. The server writes only the
 * fields that changed, under its own names, and the values are whatever JSON
 * the field holds. A screen writes them out as words and never as raw JSON.
 */
export type AuditState = Readonly<Record<string, unknown>>

/**
 * One event of the audit trail, `AuditEventView` in the contract.
 *
 * `actorUserId`, `actorName` and `actorRole` are null for an event the lazy
 * sweep wrote, which has no person behind it. `beforeState` and `afterState`
 * hold the fields that changed, and either may be null when there was no
 * record before or nothing was kept after. `requestId` ties the event to the
 * log of the request that wrote it, and is null for the sweep.
 */
export interface AuditEvent {
  id: number
  occurredAt: IsoTimestamp
  actorUserId: string | null
  actorName: string | null
  actorRole: AuditActorRole | null
  entityType: string
  entityId: string
  action: string
  beforeState: AuditState | null
  afterState: AuditState | null
  requestId: string | null
}

/**
 * The query `GET /api/admin/audit-events` accepts. Every filter may be left
 * out. `from` and `to` are days in business time. `page` counts from 1 and
 * `pageSize` is 1 to 100, and the screen always sends both.
 */
export interface AuditEventQuery {
  entityType?: string
  entityId?: string
  action?: string
  actorUserId?: string
  from?: IsoDate
  to?: IsoDate
  page: number
  pageSize: number
}

/** `GET /api/admin/audit-events`. Newest first. Read only. */
export interface AuditEventPage {
  items: AuditEvent[]
  page: number
  pageSize: number
  total: number
}

/** Where an email stands. A `FAILED` one can be sent again. */
export type NotificationStatus = 'QUEUED' | 'SENT' | 'FAILED'

/** What an email is about. This release sends booking confirmations only. */
export type NotificationType = 'BOOKING_CONFIRMATION'

/**
 * One email the system tried to send, `NotificationView` in the contract.
 *
 * `lastError` is what the mail provider said when the last attempt failed,
 * and null otherwise. `sentAt` is null until it went out. `resendOf` names the
 * failed email this one sends again, and is null for a first attempt.
 */
export interface EmailNotification {
  id: string
  reservationId: string
  reservationReference: string
  type: NotificationType
  recipientEmail: string
  subject: string
  status: NotificationStatus
  attempts: number
  lastError: string | null
  queuedAt: IsoTimestamp
  sentAt: IsoTimestamp | null
  resendOf: string | null
}

/** The query `GET /api/admin/notifications` accepts. No status means every one. */
export interface EmailNotificationQuery {
  status?: NotificationStatus
  page: number
  pageSize: number
}

/** `GET /api/admin/notifications`. Newest first. */
export interface EmailNotificationPage {
  items: EmailNotification[]
  page: number
  pageSize: number
  total: number
}

/**
 * The body of a waiver, a reversal and a force release. The reason is required
 * and is 5 to 200 characters, and the server refuses anything else with a 422
 * naming `reason`. It is kept with the charge and in the audit event.
 */
export interface CorrectionReasonRequest {
  reason: string
}

/**
 * The body `POST /api/admin/rentals/{id}/adjustments` accepts. The amount is
 * VAT inclusive, positive to charge more and negative to give money back, and
 * never zero.
 */
export interface HireAdjustmentRequest {
  amountIncVat: Money
  reason: string
}

/**
 * What 018 adds to every charge on a hire. `reversesChargeId` names the charge
 * a reversal cancels out, and is null on any other charge. `reason` is the
 * owner's reason for a waiver, a reversal or an adjustment, and null for a
 * charge the system raised.
 */
export interface ChargeCorrectionMembers {
  reversesChargeId: string | null
  reason: string | null
}

/**
 * What 018 adds to the checkout preview. The number of units the reservation
 * still needs, after a unit was released. While it is above zero the server
 * sets `canCheckOut` to false and says in `refusal` how many are missing.
 */
export interface CheckoutShortfall {
  unitsShort: number
}
