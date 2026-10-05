/**
 * SC-08 Reservation Detail and Cancellation.
 *
 * One booking in full, read from the API by the reference in the address.
 * What is on it, when it runs, where it is collected from, what it costs, and
 * whether it can still be called off. Every figure is the server's, and so is
 * the answer to whether it can be cancelled.
 *
 * A reference that belongs to another account is answered the same way as one
 * that does not exist, with a 404. The screen shows one plain "not found" for
 * both, because saying which would tell a stranger which references are real.
 *
 * Charges belong to a hire, and a hire only begins when the equipment is
 * collected. The charges card shows no figure. It says whether anything has
 * been charged, and once the equipment has gone out it points to the hire
 * history on the account page, where the charges are.
 */

import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CalendarDays, MapPin } from 'lucide-react'
import type { Reservation, ReservationStatus } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import { rememberReservation, reservationQueries } from '../../shared/api/reservation-queries'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { formatDate } from '../../shared/format'
import { ACCOUNT_PATH } from '../../shared/navigation'
import { branchDateTime } from '../../shared/today'
import { Card, EmptyState, PageHeader, StatusPill } from '../../shared/ui'
import { isNotFound } from './booking-refusal'
import { RESERVATION_STATUS_LABEL } from './customer-labels'
import { CancellationPanel } from './reservation-cancel-panel'
import { ReservationLines, ReservationTotals } from './reservation-figures'
import { MY_RESERVATIONS_PATH } from './reservation-links'

/** A booking that has not gone out yet and still may. */
const UPCOMING_STATUSES: readonly ReservationStatus[] = ['DRAFT', 'HELD', 'CONFIRMED']

/** Where the charges of a booking are, by where the booking stands. The
 *  charges belong to the hire, so once the equipment has gone out they are
 *  read on the account page with the rest of the hire history. */
function ChargesCard({ reservation }: { reservation: Reservation }) {
  if (reservation.status === 'COLLECTED' || reservation.status === 'RETURNED') {
    return (
      <Card title="Charges">
        <p className="text-sm text-slate-soft">
          {reservation.status === 'COLLECTED'
            ? 'The equipment has been collected, so this booking is now a hire.'
            : 'The equipment has come back, so this hire is finished.'}{' '}
          Its charges and where the deposit stands are in your hire history.
        </p>
        <Link to={ACCOUNT_PATH} className="btn-secondary mt-md px-md">
          See your hire history
        </Link>
      </Card>
    )
  }
  return (
    <Card title="Charges">
      <p className="text-sm text-slate-soft">
        {UPCOMING_STATUSES.includes(reservation.status)
          ? 'Nothing has been charged on this booking. The hire is charged once the equipment is collected, and its charges are then in your hire history.'
          : 'Nothing was charged on this booking, because the equipment never went out.'}
      </p>
    </Card>
  )
}

function BackLink() {
  return (
    <Link to={MY_RESERVATIONS_PATH} className="btn-ghost -ml-sm mb-sm px-sm">
      <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
      All my hires
    </Link>
  )
}

export default function ReservationDetail() {
  const { reservationId = '' } = useParams()
  const queryClient = useQueryClient()
  const reservation = useQuery({
    ...reservationQueries.detail(reservationId),
    enabled: reservationId !== '',
  })
  const phase = queryPhase(reservation)

  if (phase === 'failed' && isNotFound(reservation.error)) {
    return (
      <>
        <PageHeader screenId="SC-08" title="We cannot find that booking" />
        <div className="card">
          <EmptyState
            title="No booking with that reference"
            body="The reference may have been mistyped, or the booking may belong to a different account. Nothing has been lost."
            action={
              <Link to={MY_RESERVATIONS_PATH} className="btn-primary px-md">
                Back to my hires
              </Link>
            }
          />
        </div>
      </>
    )
  }

  if (phase === 'failed') {
    return (
      <>
        <BackLink />
        <PageHeader screenId="SC-08" title="Booking detail" />
        <ErrorState
          what="this booking"
          error={reservation.error}
          onRetry={() => void reservation.refetch()}
        />
      </>
    )
  }

  if (!reservation.data) {
    return (
      <>
        <BackLink />
        <PageHeader screenId="SC-08" title="Booking detail" />
        <LoadingState label="Loading this booking" shape="detail" count={2} />
      </>
    )
  }

  const booking = reservation.data
  const days = booking.hireDays

  return (
    <>
      <BackLink />
      <PageHeader
        screenId="SC-08"
        title={booking.reference}
        subtitle={`Booked on ${branchDateTime(booking.createdAt)} by ${booking.customerName}.`}
        actions={
          <StatusPill status={booking.status} label={RESERVATION_STATUS_LABEL[booking.status]} />
        }
      />

      <div className="grid gap-lg lg:grid-cols-3" aria-busy={reservation.isFetching}>
        <div className="flex min-w-0 flex-col gap-lg lg:col-span-2">
          <Card title="What you booked">
            <ReservationLines reservation={booking} />
            <div className="mt-lg">
              <ReservationTotals reservation={booking} />
            </div>
          </Card>

          <ChargesCard reservation={booking} />

          <CancellationPanel
            reservation={booking}
            onCancelled={(cancelled) => rememberReservation(queryClient, cancelled)}
            onOutOfDate={() => void reservation.refetch()}
          />
        </div>

        <div className="flex min-w-0 flex-col gap-lg">
          <Card title="When and where">
            {/* The icon sits inside the term. A list of terms may hold nothing
                but terms and their descriptions, so it cannot sit beside them. */}
            <dl className="flex flex-col gap-md text-sm">
              <div>
                <dt className="flex items-center gap-sm font-medium text-ink">
                  <CalendarDays className="h-5 w-5 shrink-0 text-slate-faint" aria-hidden="true" />
                  Hire period
                </dt>
                <dd className="tabular mt-xs text-slate-soft">
                  {formatDate(booking.from)} to {formatDate(booking.to)}
                </dd>
                <dd className="tabular mt-xs text-slate-soft">
                  {days} {days === 1 ? 'day' : 'days'}. The equipment is free again on the return
                  date, so bringing it back that morning costs nothing extra.
                </dd>
              </div>
              <div>
                <dt className="flex items-center gap-sm font-medium text-ink">
                  <MapPin className="h-5 w-5 shrink-0 text-slate-faint" aria-hidden="true" />
                  Collect from
                </dt>
                <dd className="mt-xs text-slate-soft">{booking.branchName}</dd>
                {UPCOMING_STATUSES.includes(booking.status) && (
                  <dd className="mt-xs text-slate-soft">
                    Bring the identity document on your account. The counter checks it before
                    anything leaves the branch.
                  </dd>
                )}
              </div>
            </dl>
          </Card>

          {(booking.holdExpiresAt !== null || booking.confirmedAt !== null) && (
            <Card title="Where it stands">
              <dl className="flex flex-col gap-sm text-sm">
                {booking.status === 'HELD' && booking.holdExpiresAt !== null && (
                  <div>
                    <dt className="font-medium text-ink">Held until</dt>
                    <dd className="tabular mt-xs text-slate-soft">
                      {branchDateTime(booking.holdExpiresAt)}
                    </dd>
                  </div>
                )}
                {booking.confirmedAt !== null && (
                  <div>
                    <dt className="font-medium text-ink">Confirmed on</dt>
                    <dd className="tabular mt-xs text-slate-soft">
                      {branchDateTime(booking.confirmedAt)}
                    </dd>
                  </div>
                )}
              </dl>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
