/**
 * One event of the audit trail on SC-24.
 *
 * Each event says what happened in words, when, and who did it in what role,
 * or that the system did it with no person behind it. It names the record it
 * is about, and lists the fields that changed as a small definition list, each
 * with how it read before and after, in words and never as raw JSON.
 *
 * Two buttons narrow the trail from the event itself, to the record it is
 * about or to the person who acted, because the owner does not know the key
 * of either and the server filters by the key.
 */

import { Filter } from 'lucide-react'
import type { AuditEvent } from '../../shared/api/contract'
import { branchDateTime } from '../../shared/today'
import { actionWords, actorWords, changeWords, changedFields, entityTypeWords } from './audit-words'

function Changes({ event }: { event: AuditEvent }) {
  const changes = changedFields(event.beforeState, event.afterState)
  if (changes.length === 0) {
    return <p className="mt-sm text-sm text-slate-soft">No field was recorded as changed.</p>
  }
  return (
    <dl className="mt-sm grid gap-xs rounded bg-muted p-sm text-sm" aria-label="What changed">
      {changes.map((change) => (
        <div key={change.field} className="grid gap-x-md sm:grid-cols-[minmax(8rem,auto)_1fr]">
          <dt className="font-medium text-ink">{change.field}</dt>
          <dd className="min-w-0 break-words text-ink">{changeWords(change)}</dd>
        </div>
      ))}
    </dl>
  )
}

export function AuditEventEntry({
  event,
  onOnlyRecord,
  onOnlyActor,
}: {
  event: AuditEvent
  /** Narrow the trail to the record this event is about. */
  onOnlyRecord: (event: AuditEvent) => void
  /** Narrow the trail to what the person behind this event did. */
  onOnlyActor: (event: AuditEvent) => void
}) {
  const titleId = `audit-event-${event.id}`
  const record = entityTypeWords(event.entityType)
  return (
    <article aria-labelledby={titleId} className="card min-w-0 p-md">
      <div className="flex flex-wrap items-baseline justify-between gap-x-md gap-y-xs">
        <h3 id={titleId} className="min-w-0 break-words text-base font-semibold text-ink">
          {actionWords(event.action)}
        </h3>
        <p className="tabular text-sm text-slate-soft">{branchDateTime(event.occurredAt)}</p>
      </div>
      <p className="mt-xs break-words text-sm text-ink">By {actorWords(event)}.</p>
      <p className="mt-xs text-sm text-slate-soft">
        {record} <span className="break-all font-mono text-xs text-ink">{event.entityId}</span>
      </p>
      <Changes event={event} />
      <div className="mt-sm flex flex-wrap gap-sm">
        <button type="button" className="btn-ghost px-sm" onClick={() => onOnlyRecord(event)}>
          <Filter className="h-4 w-4 shrink-0" aria-hidden="true" />
          Only this {record.toLowerCase()} <span className="sr-only">{event.entityId}</span>
        </button>
        {event.actorUserId !== null && event.actorName !== null && (
          <button type="button" className="btn-ghost px-sm text-left" onClick={() => onOnlyActor(event)}>
            <Filter className="h-4 w-4 shrink-0" aria-hidden="true" />
            Only what {event.actorName} did
          </button>
        )}
      </div>
      {event.requestId !== null && (
        <p className="mt-xs text-xs text-slate-soft">
          Request <span className="select-all break-all font-mono">{event.requestId}</span>
        </p>
      )}
    </article>
  )
}
