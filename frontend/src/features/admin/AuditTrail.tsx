/**
 * The audit trail table on SC-24, with its filters.
 *
 * An audit log that cannot be narrowed down is a wall of text nobody reads.
 * The filters here are the four questions actually asked after something
 * goes wrong: who did it, what kind of thing was it, when, and does this
 * word appear anywhere in it.
 */

import { useMemo, useState } from 'react'
import { RotateCcw } from 'lucide-react'
import { formatDateTime, humanise } from '../../shared/format'
import type { AuditEvent } from '../../shared/types'
import { DataTable, EmptyState, Field } from '../../shared/ui'

const SELECT_CLASS = 'field-input cursor-pointer transition-colors duration-200'
const ANY = 'ANY'

interface Filters {
  text: string
  actor: string
  action: string
  from: string
  to: string
}

const NO_FILTERS: Filters = { text: '', actor: ANY, action: ANY, from: '', to: '' }

export default function AuditTrail({ events }: { events: AuditEvent[] }) {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)

  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters((current) => ({ ...current, [key]: value }))

  const actors = useMemo(
    () => [...new Set(events.map((e) => e.actor))].sort((a, b) => a.localeCompare(b)),
    [events],
  )
  const actions = useMemo(
    () => [...new Set(events.map((e) => e.action))].sort((a, b) => a.localeCompare(b)),
    [events],
  )

  const shown = useMemo(() => {
    const needle = filters.text.trim().toLowerCase()
    return events
      .filter((e) => {
        const day = e.at.slice(0, 10)
        return (
          (needle === '' ||
            `${e.entity} ${e.detail} ${e.action} ${e.actor}`
              .toLowerCase()
              .includes(needle)) &&
          (filters.actor === ANY || e.actor === filters.actor) &&
          (filters.action === ANY || e.action === filters.action) &&
          (filters.from === '' || day >= filters.from) &&
          (filters.to === '' || day <= filters.to)
        )
      })
      .sort((a, b) => b.at.localeCompare(a.at))
  }, [events, filters])

  const filtered = JSON.stringify(filters) !== JSON.stringify(NO_FILTERS)

  return (
    <>
      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Find words in an entry" htmlFor="audit-text">
          <input
            id="audit-text"
            type="search"
            className="field-input"
            placeholder="TSH-DR-0042, or deposit"
            value={filters.text}
            onChange={(e) => set('text', e.target.value)}
          />
        </Field>
        <Field label="Who did it" htmlFor="audit-actor">
          <select
            id="audit-actor"
            className={SELECT_CLASS}
            value={filters.actor}
            onChange={(e) => set('actor', e.target.value)}
          >
            <option value={ANY}>Anybody</option>
            {actors.map((actor) => (
              <option key={actor} value={actor}>
                {actor === 'system' ? 'The system itself' : actor}
              </option>
            ))}
          </select>
        </Field>
        <Field label="What happened" htmlFor="audit-action">
          <select
            id="audit-action"
            className={SELECT_CLASS}
            value={filters.action}
            onChange={(e) => set('action', e.target.value)}
          >
            <option value={ANY}>Anything</option>
            {actions.map((action) => (
              <option key={action} value={action}>
                {humanise(action)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="From" htmlFor="audit-from">
          <input
            id="audit-from"
            type="date"
            className="field-input cursor-pointer"
            value={filters.from}
            onChange={(e) => set('from', e.target.value)}
          />
        </Field>
        <Field label="Up to and including" htmlFor="audit-to">
          <input
            id="audit-to"
            type="date"
            className="field-input cursor-pointer"
            value={filters.to}
            onChange={(e) => set('to', e.target.value)}
          />
        </Field>
      </div>

      <p className="mb-md flex flex-wrap items-center gap-md text-sm text-slate-soft">
        <span role="status">
          Showing {shown.length} of {events.length} entries
        </span>
        {filtered && (
          <button
            type="button"
            className="btn-ghost px-sm"
            onClick={() => setFilters(NO_FILTERS)}
          >
            <RotateCcw className="h-4 w-4 shrink-0" aria-hidden="true" />
            Clear the filters
          </button>
        )}
      </p>

      {shown.length === 0 ? (
        <EmptyState
          title="Nothing was recorded that matches"
          body="Widen the dates or clear the search. The trail only holds what actually happened, so an empty result usually means the filters are too narrow."
          action={
            <button
              type="button"
              className="btn-secondary px-md"
              onClick={() => setFilters(NO_FILTERS)}
            >
              Clear the filters
            </button>
          }
        />
      ) : (
        <DataTable
          columns={['When', 'Who', 'What happened', 'What it touched', 'Detail']}
          caption="Audit trail of everything the system and the staff have done"
        >
          {shown.map((event) => (
            <tr
              key={event.id}
              className="transition-colors duration-200 hover:bg-muted"
            >
              <th scope="row" className="td whitespace-nowrap text-left font-normal">
                <span className="tabular font-mono text-xs text-ink">
                  {formatDateTime(event.at)}
                </span>
              </th>
              <td className="td">
                {event.actor === 'system' ? (
                  <span className="text-slate-soft">The system itself</span>
                ) : (
                  event.actor
                )}
              </td>
              <td className="td font-medium text-ink">{humanise(event.action)}</td>
              <td className="td">
                <span className="font-mono text-xs">{event.entity}</span>
              </td>
              <td className="td min-w-[16rem] text-slate-soft">{event.detail}</td>
            </tr>
          ))}
        </DataTable>
      )}
    </>
  )
}
