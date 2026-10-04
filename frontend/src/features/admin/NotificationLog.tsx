/**
 * The notification log on SC-24.
 *
 * Every booking confirmation the system tried to send, newest first, one page
 * at a time from `GET /api/admin/notifications`. The status filter and the page
 * live in the address. A change of filter is one request, so it applies as it
 * is chosen.
 *
 * A failed email is the one a customer is left waiting on, so it says what
 * went wrong and offers "Send again" beside it. That is in
 * NotificationEntry.tsx. The log has the shared loading, failed and empty
 * states, and the server pages it.
 */

import { useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { adminQueries } from '../../shared/api/admin-queries'
import { NOTIFICATION_STATUSES } from '../../shared/api/audit-log'
import type { EmailNotificationPage } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { EmptyState, Field } from '../../shared/ui'
import { countOf } from '../counter/counter-labels'
import { notificationQueryFor, readNotificationFilters, writeNotificationFilters } from './audit-address'
import type { NotificationFilters } from './audit-address'
import { NOTIFICATION_STATUS_LABEL } from './audit-words'
import { NotificationEntry } from './NotificationEntry'
import { FIRST_PAGE } from './report-address'

const EVERY_STATUS = ''
const STATUS_FILTER_ID = 'notification-status'
const SKELETON_ROWS = 3

function statusLine(page: EmailNotificationPage, filters: NotificationFilters): string {
  const which = filters.status === null ? '' : ` that ${filters.status === 'FAILED' ? 'did not go out' : `are ${NOTIFICATION_STATUS_LABEL[filters.status].toLowerCase()}`}`
  return `${countOf(page.total, 'email', 'emails')}${which}, newest first.`
}

function Loaded({
  page,
  filters,
  onPage,
  onEvery,
}: {
  page: EmailNotificationPage
  filters: NotificationFilters
  onPage: (page: number) => void
  onEvery: () => void
}) {
  if (page.items.length === 0) {
    const pastTheEnd = page.total > 0
    return (
      <div className="card">
        <EmptyState
          title={pastTheEnd ? 'That page is past the end of the log' : 'No email matches'}
          body={
            pastTheEnd
              ? 'Go back to the first page of the log.'
              : filters.status === null
                ? 'The system has not tried to send an email yet.'
                : 'No email stands that way. Show every email to see the whole log.'
          }
          action={
            pastTheEnd ? (
              <button type="button" className="btn-secondary px-md" onClick={() => onPage(FIRST_PAGE)}>
                Go to the first page
              </button>
            ) : filters.status !== null ? (
              <button type="button" className="btn-secondary px-md" onClick={onEvery}>
                Show every email
              </button>
            ) : undefined
          }
        />
      </div>
    )
  }
  return (
    <>
      <ol className="flex flex-col gap-md" aria-label="Emails, newest first">
        {page.items.map((notification) => (
          <li key={notification.id}>
            <NotificationEntry
              notification={notification}
              original={page.items.find((candidate) => candidate.id === notification.resendOf)}
            />
          </li>
        ))}
      </ol>
      <Pagination label="Notification log pages" page={page.page} pageSize={page.pageSize} total={page.total} onPageChange={onPage} />
    </>
  )
}

export default function NotificationLog() {
  const [params, setParams] = useSearchParams()
  const filters = readNotificationFilters(params)
  const log = useQuery(adminQueries.notifications(notificationQueryFor(filters)))
  const phase = queryPhase(log)
  const regionRef = useRef<HTMLElement>(null)

  function show(changes: Partial<NotificationFilters>) {
    setParams(writeNotificationFilters({ ...filters, page: FIRST_PAGE, ...changes }), { replace: true })
  }

  function goToPage(page: number) {
    show({ page })
    regionRef.current?.focus()
  }

  return (
    <>
      <form className="card mb-lg p-lg" aria-label="Choose which emails to show" onSubmit={(e) => e.preventDefault()}>
        <div className="max-w-sm">
          <Field label="Which emails" htmlFor={STATUS_FILTER_ID}>
            <select
              id={STATUS_FILTER_ID}
              className="field-input cursor-pointer"
              value={filters.status ?? EVERY_STATUS}
              onChange={(e) => show({ status: NOTIFICATION_STATUSES.find((status) => status === e.target.value) ?? null })}
            >
              <option value={EVERY_STATUS}>Every email</option>
              {NOTIFICATION_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {NOTIFICATION_STATUS_LABEL[status]}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </form>

      <section ref={regionRef} tabIndex={-1} aria-label="The emails">
        <p role="status" className="mb-md text-sm text-slate-soft">
          {phase === 'ready' && log.data !== undefined
            ? statusLine(log.data, filters)
            : phase === 'loading'
              ? 'Loading the emails.'
              : ''}
        </p>
        {phase === 'failed' ? (
          <ErrorState what="the notification log" error={log.error} onRetry={() => void log.refetch()} />
        ) : log.data === undefined ? (
          <LoadingState shape="rows" count={SKELETON_ROWS} />
        ) : (
          <div aria-busy={log.isFetching}>
            <Loaded page={log.data} filters={filters} onPage={goToPage} onEvery={() => show({ status: null })} />
          </div>
        )}
      </section>
    </>
  )
}
