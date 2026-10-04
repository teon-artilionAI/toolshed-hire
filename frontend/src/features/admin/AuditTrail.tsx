/**
 * The audit trail on SC-24, with its filters.
 *
 * One page of events at a time from `GET /api/admin/audit-events`, newest
 * first, narrowed by the kind of record, the record, the action, the person
 * who acted and a range of days. Every filter and the page live in the
 * address under the names the API takes, so a reload or a shared link shows
 * the same events. The server does the filtering and the paging.
 *
 * Nobody can change the trail, the owner included. There is no route that
 * edits or removes an event and the database role the API runs as cannot do
 * it either, so the screen offers nothing of the kind and says so.
 *
 * It has the shared loading, failed and empty states. A refusal puts each of
 * the server's messages under the filter it names, and lists any other.
 * Moving to another page moves focus to the top of the events.
 */

import { useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { adminQueries } from '../../shared/api/admin-queries'
import type { AuditEvent, AuditEventPage } from '../../shared/api/contract'
import { fieldErrorsFromProblem, isRefusal, otherFieldMessages } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { EmptyState, Notice } from '../../shared/ui'
import { countOf } from '../counter/counter-labels'
import {
  NO_TRAIL_FILTERS,
  TRAIL_FIELDS,
  readTrailFilters,
  trailIsFiltered,
  trailQueryFor,
  writeTrailFilters,
} from './audit-address'
import type { TrailFilters } from './audit-address'
import { AuditEventEntry } from './AuditEventEntry'
import AuditFilters from './AuditFilters'
import { FIRST_PAGE } from './report-address'

const SKELETON_ROWS = 3

/** The name of the person the trail is narrowed to, from an event of theirs. */
function actorNameOn(page: AuditEventPage | undefined, actorUserId: string | null): string | null {
  if (actorUserId === null || page === undefined) return null
  return page.items.find((event) => event.actorUserId === actorUserId)?.actorName ?? null
}

function Events({
  page,
  filtered,
  onPage,
  onClear,
  onOnlyRecord,
  onOnlyActor,
}: {
  page: AuditEventPage
  filtered: boolean
  onPage: (page: number) => void
  onClear: () => void
  onOnlyRecord: (event: AuditEvent) => void
  onOnlyActor: (event: AuditEvent) => void
}) {
  if (page.items.length === 0) {
    const pastTheEnd = page.total > 0
    return (
      <div className="card">
        <EmptyState
          title={pastTheEnd ? 'That page is past the end of the trail' : 'Nothing was recorded that matches'}
          body={
            pastTheEnd
              ? 'Go back to the first page of the trail.'
              : filtered
                ? 'The trail only holds what happened, so an empty answer usually means the filters are too narrow. Widen the days or clear the filters.'
                : 'Nothing has been recorded yet.'
          }
          action={
            pastTheEnd ? (
              <button type="button" className="btn-secondary px-md" onClick={() => onPage(FIRST_PAGE)}>
                Go to the first page
              </button>
            ) : filtered ? (
              <button type="button" className="btn-secondary px-md" onClick={onClear}>
                Clear the filters
              </button>
            ) : undefined
          }
        />
      </div>
    )
  }
  return (
    <>
      <ol className="flex flex-col gap-md" aria-label="Events, newest first">
        {page.items.map((event) => (
          <li key={event.id}>
            <AuditEventEntry event={event} onOnlyRecord={onOnlyRecord} onOnlyActor={onOnlyActor} />
          </li>
        ))}
      </ol>
      <Pagination label="Audit trail pages" page={page.page} pageSize={page.pageSize} total={page.total} onPageChange={onPage} />
    </>
  )
}

export default function AuditTrail() {
  const [params, setParams] = useSearchParams()
  const filters = readTrailFilters(params)
  const trail = useQuery(adminQueries.auditEvents(trailQueryFor(filters)))
  const phase = queryPhase(trail)
  const refused = phase === 'failed' && isRefusal(trail.error)
  const fieldErrors = fieldErrorsFromProblem(trail.error)
  const otherMessages = otherFieldMessages(fieldErrors, TRAIL_FIELDS)
  const regionRef = useRef<HTMLElement>(null)

  function show(next: TrailFilters) {
    setParams(writeTrailFilters(next), { replace: true })
  }

  function goToPage(page: number) {
    show({ ...filters, page })
    regionRef.current?.focus()
  }

  const onOnlyRecord = (event: AuditEvent) =>
    show({ ...filters, entityType: event.entityType, entityId: event.entityId, page: FIRST_PAGE })
  const onOnlyActor = (event: AuditEvent) => show({ ...filters, actorUserId: event.actorUserId, page: FIRST_PAGE })

  return (
    <>
      <div className="mb-lg">
        <Notice tone="info" title="Nobody can change this record">
          <p>
            Every event is written in the same step as the change it describes. No one, the owner included, can
            edit or remove an event, and the database refuses it too. A correction is a new event of its own.
          </p>
        </Notice>
      </div>
      <AuditFilters
        filters={filters}
        fieldErrors={fieldErrors}
        actorName={actorNameOn(trail.data, filters.actorUserId)}
        onApply={show}
        onClear={() => show(NO_TRAIL_FILTERS)}
      />
      <section ref={regionRef} tabIndex={-1} aria-label="The events">
        <p role="status" className="mb-md text-sm text-slate-soft">
          {phase === 'ready' && trail.data !== undefined
            ? `${countOf(trail.data.total, 'event matches', 'events match')}, newest first.`
            : phase === 'loading'
              ? 'Loading the events.'
              : refused
                ? 'The trail was not read for those filters.'
                : ''}
        </p>
        {refused ? (
          <Notice tone="error" title="The trail cannot be read with those filters">
            <p>Check the messages under the filters above and change what they point to.</p>
            {otherMessages.length > 0 && (
              <ul className="mt-xs list-disc pl-lg">
                {otherMessages.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
          </Notice>
        ) : phase === 'failed' ? (
          <ErrorState what="the audit trail" error={trail.error} onRetry={() => void trail.refetch()} />
        ) : trail.data === undefined ? (
          <LoadingState shape="rows" count={SKELETON_ROWS} />
        ) : (
          <div aria-busy={trail.isFetching}>
            <Events
              page={trail.data}
              filtered={trailIsFiltered(filters)}
              onPage={goToPage}
              onClear={() => show(NO_TRAIL_FILTERS)}
              onOnlyRecord={onOnlyRecord}
              onOnlyActor={onOnlyActor}
            />
          </div>
        )}
      </section>
    </>
  )
}
