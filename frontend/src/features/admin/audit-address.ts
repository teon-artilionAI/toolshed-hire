/**
 * What SC-24 shows, read from the address and written back to it.
 *
 * The log has two views, the audit trail and the notification log, and the one
 * on the screen is in the address as `view`. The plain address is the trail.
 * The filters of the view and its page live in the address too, under the
 * names the API takes, so a reload or a shared link shows the same page. A
 * switch of view starts the other view afresh, with no filter and the first
 * page, so the address only ever names what is on the screen.
 *
 * A filter the address names is passed to the server as it stands, apart from
 * a day that is not a day on the calendar and a status the log does not have,
 * which are left out. Whether a filter makes sense is the server's to say,
 * with a 422 that the screen puts under the control.
 */

import type {
  AuditEventQuery,
  EmailNotificationQuery,
  IsoDate,
  NotificationStatus,
} from '../../shared/api/contract'
import { LOG_PAGE_SIZE, NOTIFICATION_STATUSES } from '../../shared/api/audit-log'
import { FIRST_PAGE, isCalendarDate } from './report-address'

/** The two views of the log. */
export type LogView = 'trail' | 'notifications'

/** The names the log keeps in the address. */
export const LOG_PARAMETER = {
  view: 'view',
  entityType: 'entityType',
  entityId: 'entityId',
  action: 'action',
  actorUserId: 'actorUserId',
  from: 'from',
  to: 'to',
  status: 'status',
  page: 'page',
} as const

/** The value of `view` for the notification log. The trail has none. */
export const NOTIFICATIONS_VIEW = 'notifications'

/** The filters of the trail that have a control on the screen, by the names
 *  the server gives them. A refusal of any other is listed apart. */
export const TRAIL_FIELDS: readonly string[] = [
  LOG_PARAMETER.entityType,
  LOG_PARAMETER.entityId,
  LOG_PARAMETER.action,
  LOG_PARAMETER.from,
  LOG_PARAMETER.to,
]

/** What the trail shows. A filter that is null is not applied. */
export interface TrailFilters {
  entityType: string | null
  entityId: string | null
  action: string | null
  actorUserId: string | null
  from: IsoDate | null
  to: IsoDate | null
  page: number
}

/** What the notification log shows. No status means every email. */
export interface NotificationFilters {
  status: NotificationStatus | null
  page: number
}

/** The trail with no filter, from its first page. */
export const NO_TRAIL_FILTERS: TrailFilters = {
  entityType: null,
  entityId: null,
  action: null,
  actorUserId: null,
  from: null,
  to: null,
  page: FIRST_PAGE,
}

function readFilter(value: string | null): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed === '' ? null : trimmed
}

function readDay(value: string | null): IsoDate | null {
  return isCalendarDate(value) ? value : null
}

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

/** Which view the address names. Anything but the notification log is the trail. */
export function readView(params: URLSearchParams): LogView {
  return params.get(LOG_PARAMETER.view) === NOTIFICATIONS_VIEW ? 'notifications' : 'trail'
}

/** Read the filters of the trail from the address. */
export function readTrailFilters(params: URLSearchParams): TrailFilters {
  return {
    entityType: readFilter(params.get(LOG_PARAMETER.entityType)),
    entityId: readFilter(params.get(LOG_PARAMETER.entityId)),
    action: readFilter(params.get(LOG_PARAMETER.action)),
    actorUserId: readFilter(params.get(LOG_PARAMETER.actorUserId)),
    from: readDay(params.get(LOG_PARAMETER.from)),
    to: readDay(params.get(LOG_PARAMETER.to)),
    page: readPage(params.get(LOG_PARAMETER.page)),
  }
}

/** Write the trail as an address. A filter not applied and the first page are left out. */
export function writeTrailFilters(filters: TrailFilters): URLSearchParams {
  const written = new URLSearchParams()
  const named: [string, string | null][] = [
    [LOG_PARAMETER.entityType, filters.entityType],
    [LOG_PARAMETER.entityId, filters.entityId],
    [LOG_PARAMETER.action, filters.action],
    [LOG_PARAMETER.actorUserId, filters.actorUserId],
    [LOG_PARAMETER.from, filters.from],
    [LOG_PARAMETER.to, filters.to],
  ]
  for (const [name, value] of named) if (value !== null) written.set(name, value)
  if (filters.page > FIRST_PAGE) written.set(LOG_PARAMETER.page, String(filters.page))
  return written
}

/** Whether any filter of the trail is applied, the page aside. */
export function trailIsFiltered(filters: TrailFilters): boolean {
  return writeTrailFilters({ ...filters, page: FIRST_PAGE }).toString() !== ''
}

/** Read the filters of the notification log from the address. */
export function readNotificationFilters(params: URLSearchParams): NotificationFilters {
  const status = params.get(LOG_PARAMETER.status)
  return {
    status: NOTIFICATION_STATUSES.find((known) => known === status) ?? null,
    page: readPage(params.get(LOG_PARAMETER.page)),
  }
}

/** Write the notification log as an address, which always names its view. */
export function writeNotificationFilters(filters: NotificationFilters): URLSearchParams {
  const written = new URLSearchParams()
  written.set(LOG_PARAMETER.view, NOTIFICATIONS_VIEW)
  if (filters.status !== null) written.set(LOG_PARAMETER.status, filters.status)
  if (filters.page > FIRST_PAGE) written.set(LOG_PARAMETER.page, String(filters.page))
  return written
}

/** The query for one page of the trail. */
export function trailQueryFor(filters: TrailFilters): AuditEventQuery {
  return {
    entityType: filters.entityType ?? undefined,
    entityId: filters.entityId ?? undefined,
    action: filters.action ?? undefined,
    actorUserId: filters.actorUserId ?? undefined,
    from: filters.from ?? undefined,
    to: filters.to ?? undefined,
    page: filters.page,
    pageSize: LOG_PAGE_SIZE,
  }
}

/** The query for one page of the notification log. */
export function notificationQueryFor(filters: NotificationFilters): EmailNotificationQuery {
  return { status: filters.status ?? undefined, page: filters.page, pageSize: LOG_PAGE_SIZE }
}

/** The address of the log on one view, from its first page with no filter. */
export function viewHref(path: string, view: LogView): string {
  return view === 'trail' ? path : `${path}?${writeNotificationFilters({ status: null, page: FIRST_PAGE }).toString()}`
}
