/**
 * The admin operations wire types. The audit trail, the notification log and
 * its re-send, and the bodies of the corrections of a charge and the release
 * of a unit.
 *
 * They are built from the generated schema the way every other wire type is,
 * so a route, a field or a value the backend changes stops the application
 * compiling until it follows. They live apart from contract.ts only to keep
 * each file a size that can be read in one sitting.
 *
 * The change also added members to two types that are built elsewhere. A
 * charge on a hire gained `reversesChargeId` and `reason`, and the checkout
 * preview gained `unitsShort`. Both come with the generated shapes that
 * contract-counter.ts already reads, so nothing here adds them.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type {
  BodyOf,
  CreatedJsonOf,
  IsoTimestamp,
  JsonOf,
  Money,
  Paths,
  QueryOf,
  Refine,
  Schemas,
} from './contract-kit'

/** The role an audit event copies from the account that acted, as the backend
 *  stores it. It is copied so the trail survives a later change of role. */
export type AuditActorRole = Schemas['UserRole']

/**
 * The fields of a record before or after a change. The server writes only the
 * fields that changed, under its own names, and the values are whatever JSON
 * the field holds. When it kept nothing on one side, such as before a record
 * was made, it sends an empty object and never null. A screen writes the
 * fields out as words and never as raw JSON.
 */
export type AuditState = Readonly<Schemas['AuditEventResponse']['beforeState']>

/**
 * One event of the audit trail.
 *
 * `actorUserId`, `actorName` and `actorRole` are null for an event the lazy
 * sweep wrote, which has no person behind it. `entityId` is the key of the
 * record the event is about. `requestId` ties the event to the log of the
 * request that wrote it, and is null for the sweep.
 */
export type AuditEvent = Refine<
  Schemas['AuditEventResponse'],
  { occurredAt: IsoTimestamp; beforeState: AuditState; afterState: AuditState }
>

/**
 * The query `GET /api/admin/audit-events` accepts.
 *
 * Every filter may be left out. `entityId` and `actorUserId` are keys, and the
 * server refuses anything else with a 422 naming the filter. `from` and `to`
 * are business days and both are included. `page` counts from 1 and
 * `pageSize` is 1 to 100. The generated type lets the page and its size be
 * left out, and the screen always sends both, so here they are required.
 */
export type AuditEventQuery = Refine<
  QueryOf<Paths['/api/admin/audit-events']['get']>,
  { page: number; pageSize: number }
>

/** `GET /api/admin/audit-events`. Newest first. Read only. */
export type AuditEventPage = Refine<JsonOf<Paths['/api/admin/audit-events']['get']>, { items: AuditEvent[] }>

/** Where an email stands. A `FAILED` one can be sent again, more than once. */
export type NotificationStatus = Schemas['NotificationStatus']

/** What an email is about. This release sends booking confirmations only. */
export type NotificationType = Schemas['NotificationType']

/**
 * One email the system tried to send, from the log and from a re-send, which
 * answers 201 with the new email. So this is built from both.
 *
 * `lastError` is what the mail provider said when the last attempt failed,
 * and null otherwise. `sentAt` is null until it went out. `resendOf` names the
 * failed email this one sends again, and is null for a first attempt. The
 * server finds it in the audit event of the re-send.
 */
export type EmailNotification = Refine<
  JsonOf<Paths['/api/admin/notifications']['get']>['items'][number] &
    CreatedJsonOf<Paths['/api/admin/notifications/{id}/resend']['post']>,
  { queuedAt: IsoTimestamp; sentAt: IsoTimestamp | null }
>

/**
 * The query `GET /api/admin/notifications` accepts. No status means every
 * one. The generated type lets the page and its size be left out, and the
 * screen always sends both, so here they are required.
 */
export type EmailNotificationQuery = Refine<
  QueryOf<Paths['/api/admin/notifications']['get']>,
  { page: number; pageSize: number }
>

/** `GET /api/admin/notifications`. Newest first. */
export type EmailNotificationPage = Refine<
  JsonOf<Paths['/api/admin/notifications']['get']>,
  { items: EmailNotification[] }
>

/**
 * The body of a waiver, a reversal and a force release. The reason is required
 * and is 5 to 200 characters, and the server refuses anything else with a 422
 * naming `reason`. It is kept with the charge and in the audit event.
 */
export type CorrectionReasonRequest = BodyOf<Paths['/api/admin/charges/{id}/waiver']['post']> &
  BodyOf<Paths['/api/admin/charges/{id}/reversal']['post']> &
  BodyOf<Paths['/api/admin/allocations/{id}/release']['post']>

/**
 * The body `POST /api/admin/rentals/{id}/adjustments` accepts. The amount is
 * VAT inclusive, positive to charge more and negative to give money back, and
 * never zero. Once a hire is settled the server only takes a negative one,
 * and refuses a positive one with a 409.
 */
export type HireAdjustmentRequest = Refine<
  BodyOf<Paths['/api/admin/rentals/{id}/adjustments']['post']>,
  { amountIncVat: Money }
>
