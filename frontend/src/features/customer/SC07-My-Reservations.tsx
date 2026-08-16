/**
 * SC-07 My Reservations.
 *
 * Everything a customer has booked, split into what is still live and what
 * is finished, and filterable by status on top of that. The split is by
 * status rather than by date, because a booking that was due back on Tuesday
 * and is still sitting on a site in Salt River is very much current.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { branches, reservations } from '../../shared/fixtures'
import { formatDate, isOverdue } from '../../shared/format'
import type { Reservation, ReservationStatus } from '../../shared/types'
import {
  DataTable,
  EmptyState,
  Notice,
  PageHeader,
  StatTile,
} from '../../shared/ui'
import { SignInRequired, useCustomerProfile } from './customer-session'
import { CURRENT_STATUSES, RESERVATION_STATUS_LABEL } from './customer-labels'
import { rentalForReservation } from './reservation-maths'
import { ReservationRow } from './reservation-row'

type Tab = 'current' | 'past'

const TAB_LABEL: Record<Tab, string> = {
  current: 'Current and upcoming',
  past: 'Finished and cancelled',
}

const ALL = 'ALL'

function isCurrent(reservation: Reservation): boolean {
  return CURRENT_STATUSES.includes(reservation.status)
}

function branchName(code: Reservation['branchCode']): string {
  return branches.find((branch) => branch.code === code)?.name ?? code
}

export default function MyReservations() {
  const customer = useCustomerProfile()
  const [tab, setTab] = useState<Tab>('current')
  const [status, setStatus] = useState<string>(ALL)

  const mine = useMemo(
    () =>
      customer
        ? reservations
            .filter((reservation) => reservation.customerId === customer.id)
            .sort((a, b) => b.startDate.localeCompare(a.startDate))
        : [],
    [customer],
  )

  const inTab = mine.filter((reservation) =>
    tab === 'current' ? isCurrent(reservation) : !isCurrent(reservation),
  )
  const statusesInTab = Array.from(
    new Set(inTab.map((reservation) => reservation.status)),
  )
  const visible =
    status === ALL
      ? inTab
      : inTab.filter((reservation) => reservation.status === status)

  const overdueRental = mine
    .map(rentalForReservation)
    .find((rental) => rental && isOverdue(rental.dueBackOn))

  if (!customer) {
    return (
      <>
        <PageHeader screenId="SC-07" title="My hires" />
        <SignInRequired what="your hires" />
      </>
    )
  }

  const currentCount = mine.filter(isCurrent).length

  return (
    <>
      <PageHeader
        screenId="SC-07"
        title="My hires"
        subtitle={`Every booking on the account for ${customer.name}.`}
        actions={
          <Link to="/" className="btn-primary px-md">
            Book more equipment
          </Link>
        }
      />

      {overdueRental && (
        <div className="mb-lg">
          <Notice tone="error" title="Something is overdue">
            <p>
              Hire {overdueRental.reference} was due back on{' '}
              {formatDate(overdueRental.dueBackOn)}. A late fee is added for
              every day it stays out. Bring it back to{' '}
              {branchName(overdueRental.branchCode)} to stop the charge.
            </p>
          </Notice>
        </div>
      )}

      <div className="mb-lg grid gap-md sm:grid-cols-3">
        <StatTile
          label="Live bookings"
          value={currentCount}
          hint="Confirmed, held or out on hire"
        />
        <StatTile
          label="Finished"
          value={mine.length - currentCount}
          hint="Closed, cancelled or not collected"
        />
        <StatTile
          label="Bookings in total"
          value={mine.length}
          hint={`Since ${formatDate(customer.joinedOn)}`}
        />
      </div>

      <div className="mb-md flex flex-wrap items-end justify-between gap-md">
        <div
          className="flex flex-wrap gap-sm"
          role="group"
          aria-label="Which bookings to show"
        >
          {(Object.keys(TAB_LABEL) as Tab[]).map((key) => {
            const active = tab === key
            const count = mine.filter((reservation) =>
              key === 'current' ? isCurrent(reservation) : !isCurrent(reservation),
            ).length
            return (
              <button
                key={key}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  setTab(key)
                  setStatus(ALL)
                }}
                className={`btn px-md ${
                  active
                    ? 'bg-accent font-semibold text-accent-ink'
                    : 'border border-line bg-surface text-slate hover:bg-muted hover:text-ink'
                }`}
              >
                {TAB_LABEL[key]}
                <span className="tabular text-xs">({count})</span>
              </button>
            )
          })}
        </div>

        <div className="min-w-[14rem]">
          <label className="field-label" htmlFor="reservation-status">
            Filter by status
          </label>
          <select
            id="reservation-status"
            className="field-input cursor-pointer"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value={ALL}>Any status ({inTab.length})</option>
            {statusesInTab.map((value) => (
              <option key={value} value={value}>
                {RESERVATION_STATUS_LABEL[value as ReservationStatus]} (
                {inTab.filter((r) => r.status === value).length})
              </option>
            ))}
          </select>
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="card">
          <EmptyState
            title={
              status === ALL
                ? `Nothing under ${TAB_LABEL[tab].toLowerCase()}`
                : 'No bookings match that status'
            }
            body={
              status === ALL
                ? 'When you book equipment it will appear here, with the collection branch and the dates.'
                : 'Try a different status, or clear the filter to see everything in this tab.'
            }
            action={
              status === ALL ? (
                <Link to="/" className="btn-primary px-md">
                  Browse the catalogue
                </Link>
              ) : (
                <button
                  type="button"
                  className="btn-secondary px-md"
                  onClick={() => setStatus(ALL)}
                >
                  Clear the filter
                </button>
              )
            }
          />
        </div>
      ) : (
        <DataTable
          caption={`${TAB_LABEL[tab]} bookings for ${customer.name}`}
          columns={[
            'Booking',
            'Hire dates',
            'Collect from',
            'Status',
            'Details',
          ]}
        >
          {visible.map((reservation) => (
            <ReservationRow key={reservation.id} reservation={reservation} />
          ))}
        </DataTable>
      )}
    </>
  )
}
