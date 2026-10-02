/**
 * One booking as a row in the SC-07 list.
 *
 * The reference and the contents share a cell, and the dates carry the day
 * count, so the table stays narrow enough to read on a phone. Every value is
 * the server's. The total is the one the reservation was priced at, and the
 * count of days is the one the server sent with it.
 *
 * The link is by reference, because that is what a customer quotes and what
 * the detail screen is addressed by.
 */

import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import type { Reservation } from '../../shared/api/contract'
import { formatDate, formatDateShort, money } from '../../shared/format'
import { branchClockTime } from '../../shared/today'
import { StatusPill } from '../../shared/ui'
import { RESERVATION_STATUS_LABEL } from './customer-labels'
import { reservationHref } from './reservation-links'

/** What is on a booking, for example "2 x CP 100 Plate Compactor". */
function itemsSummary(reservation: Reservation): string {
  return reservation.lines.map((line) => `${line.quantity} x ${line.modelName}`).join(', ')
}

export function ReservationRow({ reservation }: { reservation: Reservation }) {
  const { hireDays } = reservation
  return (
    <tr className="transition-colors duration-200 hover:bg-muted">
      <td className="td">
        <p className="whitespace-nowrap font-mono text-sm font-medium text-ink">{reservation.reference}</p>
        <p className="mt-xs max-w-xs text-sm text-slate-soft">{itemsSummary(reservation)}</p>
      </td>
      <td className="td whitespace-nowrap">
        <p className="tabular text-sm text-ink">
          {formatDateShort(reservation.from)} to {formatDate(reservation.to)}
        </p>
        <p className="tabular mt-xs text-sm text-slate-soft">
          {hireDays} {hireDays === 1 ? 'day' : 'days'}
        </p>
      </td>
      <td className="td">
        <p className="text-sm text-ink">{reservation.branchName}</p>
      </td>
      <td className="td">
        <StatusPill status={reservation.status} label={RESERVATION_STATUS_LABEL[reservation.status]} />
        {reservation.status === 'HELD' && reservation.holdExpiresAt !== null && (
          <p className="tabular mt-xs text-sm text-slate-soft">
            Until {branchClockTime(reservation.holdExpiresAt)}
          </p>
        )}
      </td>
      <td className="td tabular whitespace-nowrap text-sm font-medium text-ink">
        {money(reservation.estimatedTotalIncVat)}
      </td>
      <td className="td">
        <Link to={reservationHref(reservation.reference)} className="btn-secondary whitespace-nowrap px-md">
          View
          <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />{' '}
          <span className="sr-only">booking {reservation.reference}</span>
        </Link>
      </td>
    </tr>
  )
}
