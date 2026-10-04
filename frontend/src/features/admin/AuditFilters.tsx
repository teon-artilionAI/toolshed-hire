/**
 * The filters above the audit trail on SC-24.
 *
 * The kind of record, the record itself by its key, the action, and a range
 * of days. The text boxes would ask the server on every key, so the filters
 * are applied together with one button, and the address then says what is
 * shown. The form follows the address when the address changes, such as after
 * the back button or a button on an event.
 *
 * The server narrows to one record by its key and by nothing else, so a
 * reference typed in the box is not sent. The box says so under itself and
 * nothing is applied until it holds a key or is cleared. The button on an
 * event fills the key in, which is the usual way to get one.
 *
 * The person who acted is narrowed from an event, because the server filters
 * by the key of the account and nobody knows that by heart. While it applies,
 * a line above the button says so and offers to show everybody again.
 *
 * When the server refuses a filter, its message is under the control it is
 * about.
 */

import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Search, UserRound, X } from 'lucide-react'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { DateInput, SelectInput, TextInput } from '../counter/counter-fields'
import { isRecordKey, writeTrailFilters } from './audit-address'
import type { TrailFilters } from './audit-address'
import { ENTITY_TYPE_LABEL, entityTypeWords } from './audit-words'
import { FIRST_PAGE } from './report-address'

const ANY_RECORD = ''

/** The earliest day the date pickers open on. Nothing was recorded before the
 *  system went live in 2026, so an earlier day can only find nothing. */
const EARLIEST_DAY = '2026-01-01'

/** Said under the record box when it holds something that is not a key. */
const NOT_A_RECORD_KEY =
  'Enter the key of a record as an event shows it, such as 5f0c2a9e-0000-4000-8000-000000000124. ' +
  'A booking or hire reference is not a key. Press "Only this" on one of its events instead.'

/** What the person is typing, before it is applied. */
interface Draft {
  entityType: string
  entityId: string
  action: string
  from: string
  to: string
}

function draftOf(filters: TrailFilters): Draft {
  return {
    entityType: filters.entityType ?? ANY_RECORD,
    entityId: filters.entityId ?? '',
    action: filters.action ?? '',
    from: filters.from ?? '',
    to: filters.to ?? '',
  }
}

function given(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

function recordOptions(chosen: string): { value: string; label: string }[] {
  const known = Object.keys(ENTITY_TYPE_LABEL).map((type) => ({ value: type, label: ENTITY_TYPE_LABEL[type] }))
  const unknown = chosen !== ANY_RECORD && !(chosen in ENTITY_TYPE_LABEL) ? [{ value: chosen, label: entityTypeWords(chosen) }] : []
  return [{ value: ANY_RECORD, label: 'Any kind of record' }, ...known, ...unknown]
}

export default function AuditFilters({
  filters,
  fieldErrors,
  actorName,
  onApply,
  onClear,
}: {
  filters: TrailFilters
  fieldErrors: FieldErrors
  /** The name of the person the trail is narrowed to, once an event has said it. */
  actorName: string | null
  onApply: (filters: TrailFilters) => void
  onClear: () => void
}) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(filters))
  const [keyRefused, setKeyRefused] = useState(false)
  const recordBox = useRef<HTMLInputElement>(null)
  const addressSays = writeTrailFilters(filters).toString()
  const [lastAddress, setLastAddress] = useState(addressSays)
  if (addressSays !== lastAddress) {
    setLastAddress(addressSays)
    setDraft(draftOf(filters))
    setKeyRefused(false)
  }

  function patch(change: Partial<Draft>) {
    setDraft((current) => ({ ...current, ...change }))
  }

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const entityId = given(draft.entityId)
    if (entityId !== null && !isRecordKey(entityId)) {
      setKeyRefused(true)
      recordBox.current?.focus()
      return
    }
    setKeyRefused(false)
    onApply({
      entityType: given(draft.entityType),
      entityId,
      action: given(draft.action),
      actorUserId: filters.actorUserId,
      from: given(draft.from),
      to: given(draft.to),
      page: FIRST_PAGE,
    })
  }

  return (
    <form noValidate className="card mb-lg p-lg" aria-label="Narrow the audit trail" onSubmit={apply}>
      <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-3">
        <SelectInput
          id="audit-entity-type"
          label="Kind of record"
          value={draft.entityType}
          onChange={(entityType) => patch({ entityType })}
          options={recordOptions(draft.entityType)}
          error={fieldErrors.entityType}
        />
        <TextInput
          id="audit-entity-id"
          label="Record key"
          help={'The key an event shows. "Only this" on an event fills it in.'}
          value={draft.entityId}
          onChange={(entityId) => {
            setKeyRefused(false)
            patch({ entityId })
          }}
          error={keyRefused ? NOT_A_RECORD_KEY : fieldErrors.entityId}
          autoComplete="off"
          inputRef={recordBox}
        />
        <TextInput
          id="audit-action"
          label="Action"
          help="As the system names it, for example reservation.confirmed."
          value={draft.action}
          onChange={(action) => patch({ action })}
          error={fieldErrors.action}
          autoComplete="off"
        />
        <DateInput
          id="audit-from"
          label="From"
          value={draft.from}
          onChange={(from) => patch({ from })}
          error={fieldErrors.from}
          min={EARLIEST_DAY}
        />
        <DateInput
          id="audit-to"
          label="To"
          value={draft.to}
          onChange={(to) => patch({ to })}
          error={fieldErrors.to}
          min={EARLIEST_DAY}
        />
      </div>
      {filters.actorUserId !== null && (
        <p className="mt-md flex flex-wrap items-center gap-sm rounded bg-muted px-md py-xs text-sm text-ink">
          <UserRound className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words">
            Only what {actorName ?? 'one person'} did.
          </span>
          <button
            type="button"
            className="btn-ghost px-sm"
            onClick={() => onApply({ ...filters, actorUserId: null, page: FIRST_PAGE })}
          >
            <X className="h-4 w-4 shrink-0" aria-hidden="true" />
            Show everybody
          </button>
        </p>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md">
          <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
          Show these events
        </button>
        <button type="button" className="btn-secondary px-md" onClick={onClear}>
          Clear the filters
        </button>
      </div>
    </form>
  )
}
