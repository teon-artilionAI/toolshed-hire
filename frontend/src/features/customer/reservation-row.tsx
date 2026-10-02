/**
 * One booking as a row in the SC-07 list.
 *
 * The reference and the contents share a cell, and the dates carry the day
 * count, so the table stays narrow enough to read. Every value is the
 * server's. The total is the one the reservation was priced at, and the
 * count of days is the one the server sent with it.
 *
 * Below the `sm` width the row is drawn as a block and each cell as a line of
 * its own, with the name of its column beside the value. That is the same
 * row and the same cells, drawn differently, and reservation-table.tsx says
 * why. Each cell states its role for the same reason the table does.
 *
 * The link is by reference, because that is what a customer quotes and what
 * the detail screen is addressed by.
 */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import type { Reservation } from '../../shared/api/contract'
import { formatDate, formatDateShort, money } from '../../shared/format'
import { branchClockTime } from '../../shared/today'
import { StatusPill } from '../../shared/ui'
import { RESERVATION_STATUS_LABEL } from './customer-labels'
import { RESERVATION_COLUMN } from './reservation-columns'
import { reservationHref } from './reservation-links'

/** What every cell shares. A table cell from `sm` up, and tighter on a phone. */
const CELL_BASE = 'td px-0 py-xs sm:table-cell sm:px-md sm:py-sm'

/** A cell that is a plain block on a phone. */
const CELL = `${CELL_BASE} block`

/** A cell that shows the name of its column beside its value on a phone. */
const LABELLED_CELL = `${CELL_BASE} flex items-baseline justify-between gap-md`

/** What is on a booking, for example "2 x CP 100 Plate Compactor". */
function itemsSummary(reservation: Reservation): string {
  return reservation.lines.map((line) => `${line.quantity} x ${line.modelName}`).join(', ')
}

/** The name of a column, shown only where the headings are not. */
function ColumnName({ children }: { children: ReactNode }) {
  return <span className="shrink-0 text-sm text-slate-soft sm:hidden">{children}</span>
}

export function ReservationRow({ reservation }: { reservation: Reservation }) {
  const { hireDays } = reservation
  return (
    <tr
      role="row"
      className="block px-md py-sm transition-colors duration-200 hover:bg-muted sm:table-row"
    >
      <td role="cell" className={CELL}>
        <p className="whitespace-nowrap font-mono text-sm font-medium text-ink">{reservation.reference}</p>
        <p className="mt-xs max-w-xs text-sm text-slate-soft">{itemsSummary(reservation)}</p>
      </td>
      <td role="cell" className={`${LABELLED_CELL} whitespace-nowrap`}>
        <ColumnName>{RESERVATION_COLUMN.dates}</ColumnName>
        <div className="text-right sm:text-left">
          <p className="tabular text-sm text-ink">
            {formatDateShort(reservation.from)} to {formatDate(reservation.to)}
          </p>
          <p className="tabular mt-xs text-sm text-slate-soft">
            {hireDays} {hireDays === 1 ? 'day' : 'days'}
          </p>
        </div>
      </td>
      <td role="cell" className={LABELLED_CELL}>
        <ColumnName>{RESERVATION_COLUMN.branch}</ColumnName>
        <p className="text-right text-sm text-ink sm:text-left">{reservation.branchName}</p>
      </td>
      <td role="cell" className={LABELLED_CELL}>
        <ColumnName>{RESERVATION_COLUMN.status}</ColumnName>
        <div className="text-right sm:text-left">
          <StatusPill status={reservation.status} label={RESERVATION_STATUS_LABEL[reservation.status]} />
          {reservation.status === 'HELD' && reservation.holdExpiresAt !== null && (
            <p className="tabular mt-xs text-sm text-slate-soft">
              Until {branchClockTime(reservation.holdExpiresAt)}
            </p>
          )}
        </div>
      </td>
      <td role="cell" className={`${LABELLED_CELL} whitespace-nowrap`}>
        <ColumnName>{RESERVATION_COLUMN.total}</ColumnName>
        <span className="tabular text-sm font-medium text-ink">{money(reservation.estimatedTotalIncVat)}</span>
      </td>
      <td role="cell" className={`${CELL} pt-sm`}>
        <Link to={reservationHref(reservation.reference)} className="btn-secondary whitespace-nowrap px-md">
          View
          <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />{' '}
          <span className="sr-only">booking {reservation.reference}</span>
        </Link>
      </td>
    </tr>
  )
}
