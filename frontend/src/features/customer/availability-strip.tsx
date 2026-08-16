/**
 * The fourteen day availability strip used on SC-03.
 *
 * A single number for a period tells a customer whether they can have the
 * tool. It does not tell them when it frees up, which is the question they
 * actually ask at the counter. So the strip lays the next fortnight out
 * day by day and branch by branch, and marks the days they have currently
 * chosen so the two readings line up.
 *
 * It is a real table. Days are column headers, branches are row headers,
 * and every cell carries the count as text as well as a tone, so the strip
 * survives greyscale printing and colour blindness.
 */

import { branches } from '../../shared/fixtures'
import type { Uuid } from '../../shared/types'
import { formatDate } from '../../shared/format'
import { availabilityStrip } from './availability'
import { AVAILABILITY_HORIZON_DAYS } from './hire-period'

const WEEKDAY = new Intl.DateTimeFormat('en-ZA', { weekday: 'short' })
const DAY_OF_MONTH = new Intl.DateTimeFormat('en-ZA', { day: 'numeric' })

type CellTone = 'free' | 'some' | 'none'

const CELL_CLASS: Record<CellTone, string> = {
  free: 'bg-status-available-wash text-status-available',
  some: 'bg-status-due-wash text-status-due',
  none: 'bg-status-overdue-wash text-status-overdue',
}

const LEGEND: { tone: CellTone; label: string }[] = [
  { tone: 'free', label: 'Every unit free' },
  { tone: 'some', label: 'Some units left' },
  { tone: 'none', label: 'None free' },
]

function toneFor(available: number, serviceable: number): CellTone {
  if (available <= 0) return 'none'
  return available < serviceable ? 'some' : 'free'
}

export default function AvailabilityStrip({
  modelId,
  fromIso,
  startIso,
  endIso,
  days = AVAILABILITY_HORIZON_DAYS,
}: {
  modelId: Uuid
  /** First day the strip shows. */
  fromIso: string
  /** The customer's chosen collection date, marked on the strip. */
  startIso: string
  /** The customer's chosen return date, exclusive. */
  endIso: string
  days?: number
}) {
  const rows = branches.map((branch) => ({
    branch,
    cells: availabilityStrip(modelId, branch.code, fromIso, days),
  }))
  const columns = rows[0]?.cells ?? []

  return (
    <div>
      {/* `relative` matters. The cells carry visually hidden text, which is
          absolutely positioned, and an absolutely positioned box escapes the
          overflow clipping of any ancestor that is not itself positioned.
          Without this the hidden text pushes the whole page sideways at
          375px instead of scrolling inside the table. */}
      <div className="table-wrap relative">
        <table className="w-full border-collapse">
          <caption className="sr-only">
            Units free each day for the next {days} days, by branch. Your chosen days are
            marked.
          </caption>
          <thead className="border-b border-line bg-muted">
            <tr>
              <th scope="col" className="th sticky left-0 z-10 bg-muted">
                Branch
              </th>
              {columns.map((cell) => {
                const date = new Date(`${cell.date}T00:00:00Z`)
                const chosen = cell.date >= startIso && cell.date < endIso
                return (
                  <th
                    key={cell.date}
                    scope="col"
                    className={`th min-w-[3rem] text-center ${
                      chosen ? 'bg-accent-wash text-ink' : ''
                    }`}
                  >
                    <span className="block text-xs font-normal normal-case">
                      {WEEKDAY.format(date)}
                    </span>
                    <span className="tabular block text-sm">{DAY_OF_MONTH.format(date)}</span>
                    {chosen && <span className="sr-only">, one of your chosen days</span>}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map(({ branch, cells }) => (
              <tr key={branch.code}>
                <th
                  scope="row"
                  className="td sticky left-0 z-10 whitespace-nowrap bg-surface font-semibold text-ink"
                >
                  {branch.name}
                </th>
                {cells.map((cell) => {
                  const tone = toneFor(cell.availableUnits, cell.serviceableUnits)
                  const chosen = cell.date >= startIso && cell.date < endIso
                  return (
                    <td key={cell.date} className="p-xs text-center">
                      <span
                        className={`tabular flex h-11 min-w-[2.75rem] items-center justify-center rounded text-sm font-semibold ${
                          CELL_CLASS[tone]
                        } ${chosen ? 'ring-2 ring-inset ring-ink' : ''}`}
                      >
                        {cell.availableUnits}
                        <span className="sr-only">
                          {' '}
                          free at {branch.name} on {formatDate(cell.date)}
                        </span>
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="mt-md flex flex-wrap items-center gap-md text-sm text-slate-soft">
        {LEGEND.map(({ tone, label }) => (
          <li key={tone} className="flex items-center gap-sm">
            <span
              className={`h-5 w-5 shrink-0 rounded ${CELL_CLASS[tone]}`}
              aria-hidden="true"
            />
            {label}
          </li>
        ))}
        <li className="flex items-center gap-sm">
          <span
            className="h-5 w-5 shrink-0 rounded bg-surface ring-2 ring-inset ring-ink"
            aria-hidden="true"
          />
          Your chosen days
        </li>
      </ul>
    </div>
  )
}
