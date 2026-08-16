/**
 * SC-08 Reservation Detail and Cancellation.
 *
 * One booking in full: what is on it, when it runs, where it is collected
 * from, what it costs, and whether it can still be called off. Cancelling
 * changes the status in this session only, which is what a prototype with
 * no back end can honestly promise.
 */

import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CalendarDays, MapPin } from 'lucide-react'
import { branches, reservations } from '../../shared/fixtures'
import { formatDate, formatDateTime, money } from '../../shared/format'
import type { ReservationStatus } from '../../shared/types'
import {
  Card,
  DataTable,
  EmptyState,
  Notice,
  PageHeader,
  StatusPill,
} from '../../shared/ui'
import { SignInRequired, useCustomerProfile } from './customer-session'
import { RESERVATION_STATUS_LABEL } from './customer-labels'
import { CancellationPanel } from './reservation-cancel-panel'
import { HireProgressCard } from './reservation-hire-card'
import {
  depositTotal,
  hireDays,
  hireSubtotal,
  lineTotal,
  modelFor,
  rentalForReservation,
} from './reservation-maths'

function BackLink() {
  return (
    <Link to="/reservations" className="btn-ghost -ml-sm mb-sm px-sm">
      <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
      All my hires
    </Link>
  )
}

export default function ReservationDetail() {
  const { reservationId } = useParams()
  const customer = useCustomerProfile()
  const [cancelledReason, setCancelledReason] = useState<string | null>(null)

  const reservation = reservations.find(
    (candidate) =>
      candidate.id === reservationId || candidate.reference === reservationId,
  )

  if (!customer) {
    return (
      <>
        <PageHeader screenId="SC-08" title="Booking detail" />
        <SignInRequired what="this booking" />
      </>
    )
  }

  if (!reservation) {
    return (
      <>
        <PageHeader screenId="SC-08" title="We cannot find that booking" />
        <div className="card">
          <EmptyState
            title="No booking with that reference"
            body="The reference may have been mistyped, or the booking may belong to a different account. Nothing has been lost."
            action={
              <Link to="/reservations" className="btn-primary px-md">
                Back to my hires
              </Link>
            }
          />
        </div>
      </>
    )
  }

  const status: ReservationStatus = cancelledReason
    ? 'CANCELLED'
    : reservation.status
  const branch =
    branches.find((candidate) => candidate.code === reservation.branchCode) ??
    branches[0]
  const days = hireDays(reservation)
  const subtotal = hireSubtotal(reservation)
  const deposit = depositTotal(reservation)
  const rental = rentalForReservation(reservation)

  return (
    <>
      <BackLink />
      <PageHeader
        screenId="SC-08"
        title={reservation.reference}
        subtitle={`Booked on ${formatDateTime(reservation.createdAt)} by ${customer.name}.`}
        actions={
          <StatusPill status={status} label={RESERVATION_STATUS_LABEL[status]} />
        }
      />

      {cancelledReason && (
        <div className="mb-lg">
          <Notice tone="success" title="This booking has been cancelled">
            <p>
              We have noted the reason as "{cancelledReason.toLowerCase()}". The
              equipment is back in stock at {branch.name} and nothing is owed.
              A confirmation is on its way to {customer.email}.
            </p>
          </Notice>
        </div>
      )}

      <div className="grid gap-lg lg:grid-cols-3">
        <div className="flex flex-col gap-lg lg:col-span-2">
          <Card title="What you booked">
            <DataTable
              caption={`Items on booking ${reservation.reference}`}
              columns={['Equipment', 'Units', 'Per day', 'Days', 'Hire total']}
            >
              {reservation.lines.map((line) => {
                const model = modelFor(line)
                return (
                  <tr key={line.id}>
                    <td className="td">
                      <p className="text-sm font-medium text-ink">
                        {model
                          ? `${model.manufacturer} ${model.name}`
                          : 'Item withdrawn from the catalogue'}
                      </p>
                      {line.allocatedAssetIds.length > 0 && (
                        <p className="mt-xs font-mono text-xs text-slate-soft">
                          Set aside for you
                        </p>
                      )}
                      <p className="mt-xs text-sm text-slate-soft">
                        {money(line.depositPerUnitSnapshot)} deposit each
                      </p>
                    </td>
                    <td className="td tabular">{line.quantity}</td>
                    <td className="td tabular whitespace-nowrap">
                      {money(line.ratePerDaySnapshot)}
                    </td>
                    <td className="td tabular">{days}</td>
                    <td className="td tabular whitespace-nowrap font-medium">
                      {money(lineTotal(line, days))}
                    </td>
                  </tr>
                )
              })}
            </DataTable>

            <dl className="mt-lg flex flex-col gap-sm text-sm">
              <div className="flex justify-between gap-md">
                <dt className="text-slate-soft">Hire charge</dt>
                <dd className="tabular font-medium text-ink">
                  {money(subtotal)}
                </dd>
              </div>
              <div className="flex justify-between gap-md">
                <dt className="text-slate-soft">
                  Refundable deposit, taken at collection
                </dt>
                <dd className="tabular font-medium text-ink">
                  {money(deposit)}
                </dd>
              </div>
              <div className="flex justify-between gap-md border-t border-line pt-sm">
                <dt className="font-medium text-ink">Due at the counter</dt>
                <dd className="tabular text-lg font-semibold text-ink">
                  {money(subtotal + deposit)}
                </dd>
              </div>
            </dl>
          </Card>

          {rental && <HireProgressCard rental={rental} />}

          <CancellationPanel
            reservation={reservation}
            status={status}
            branch={branch}
            onCancel={setCancelledReason}
          />
        </div>

        <div className="flex flex-col gap-lg">
          <Card title="When and where">
            <dl className="flex flex-col gap-md text-sm">
              <div className="flex items-start gap-sm">
                <CalendarDays
                  className="mt-xs h-5 w-5 shrink-0 text-slate-faint"
                  aria-hidden="true"
                />
                <div>
                  <dt className="font-medium text-ink">Hire period</dt>
                  <dd className="tabular mt-xs text-slate-soft">
                    {formatDate(reservation.startDate)} to{' '}
                    {formatDate(reservation.endDate)}
                  </dd>
                  <dd className="tabular mt-xs text-slate-soft">
                    {days} {days === 1 ? 'day' : 'days'}. The equipment is free
                    again on the return date, so bringing it back that morning
                    costs nothing extra.
                  </dd>
                </div>
              </div>
              <div className="flex items-start gap-sm">
                <MapPin
                  className="mt-xs h-5 w-5 shrink-0 text-slate-faint"
                  aria-hidden="true"
                />
                <div>
                  <dt className="font-medium text-ink">Collect from</dt>
                  <dd className="mt-xs text-slate-soft">
                    {branch.name}, {branch.suburb}
                  </dd>
                  <dd className="mt-xs text-slate-soft">
                    Bring the identity document on your account. The counter
                    checks it before anything leaves the branch.
                  </dd>
                </div>
              </div>
            </dl>
          </Card>

          {reservation.notes && (
            <Card title="Notes on this booking">
              <p className="text-sm text-slate-soft">{reservation.notes}</p>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
