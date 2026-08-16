/**
 * One booking as a row in the SC-07 list.
 *
 * The reference and the contents share a cell, and the dates carry the day
 * count and the hire charge, so the table stays five columns wide and does
 * not need side scrolling on a phone held in one hand.
 */

import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { branches } from '../../shared/fixtures'
import { formatDate, formatDateShort, isOverdue, money } from '../../shared/format'
import type { Reservation } from '../../shared/types'
import { StatusPill } from '../../shared/ui'
import { RESERVATION_STATUS_LABEL } from './customer-labels'
import { hireDays, hireSubtotal, itemsSummary, rentalForReservation } from './reservation-maths'

export function ReservationRow({ reservation }: { reservation: Reservation }) {
  const days = hireDays(reservation)
  const rental = rentalForReservation(reservation)
  const late = rental ? isOverdue(rental.dueBackOn) : false
  const branch = branches.find(
    (candidate) => candidate.code === reservation.branchCode,
  )

  return (
    <tr className="transition-colors duration-200 hover:bg-muted">
      <td className="td">
        <p className="font-mono text-sm font-medium text-ink">
          {reservation.reference}
        </p>
        <p className="mt-xs max-w-xs text-sm text-slate-soft">
          {itemsSummary(reservation)}
        </p>
      </td>
      <td className="td whitespace-nowrap">
        <p className="tabular text-sm text-ink">
          {formatDateShort(reservation.startDate)} to{' '}
          {formatDate(reservation.endDate)}
        </p>
        <p className="tabular mt-xs text-sm text-slate-soft">
          {days} {days === 1 ? 'day' : 'days'} at {money(hireSubtotal(reservation))}
        </p>
      </td>
      <td className="td">
        <p className="text-sm text-ink">{branch?.name}</p>
        <p className="mt-xs text-sm text-slate-soft">{branch?.suburb}</p>
      </td>
      <td className="td">
        <StatusPill
          status={reservation.status}
          label={RESERVATION_STATUS_LABEL[reservation.status]}
        />
        {rental && (
          <p
            className={`tabular mt-xs text-sm ${
              late ? 'font-medium text-status-overdue' : 'text-slate-soft'
            }`}
          >
            {late ? 'Was due back ' : 'Due back '}
            {formatDate(rental.dueBackOn)}
          </p>
        )}
      </td>
      <td className="td">
        <Link
          to={`/reservations/${reservation.id}`}
          className="btn-secondary whitespace-nowrap px-md"
        >
          View
          <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="sr-only"> booking {reservation.reference}</span>
        </Link>
      </td>
    </tr>
  )
}
