/**
 * SC-09 My Account and Hire History.
 *
 * Profile, past hires, charges and the deposit position on one screen. The
 * deposit is the question customers actually ring up about, so it is stated
 * as arithmetic rather than left to be worked out: this much is held, this
 * much is coming off, this much comes back.
 */

import { Link } from 'react-router-dom'
import { charges, rentals, reservations } from '../../shared/fixtures'
import {
  daysOverdue,
  formatDate,
  formatDateShort,
  isOverdue,
  money,
} from '../../shared/format'
import type { Charge, Rental } from '../../shared/types'
import {
  Card,
  DataTable,
  EmptyState,
  Notice,
  PageHeader,
  StatTile,
  StatusPill,
} from '../../shared/ui'
import { AccountProfileCard } from './account-profile-card'
import { SignInRequired, useCustomerProfile } from './customer-session'
import { CHARGE_KIND_LABEL, RENTAL_STATUS_LABEL } from './customer-labels'

/** A hire is only finished, and its deposit only released, once the account
 *  is settled. Anything short of that still has money on it. */
function isSettled(rental: Rental): boolean {
  return rental.status === 'SETTLED'
}

/** A deposit is money held, not money owed, so it never counts as an
 *  outstanding charge. */
function isOutstanding(charge: Charge): boolean {
  return !charge.settled && charge.kind !== 'DEPOSIT'
}

function referenceForRental(rental: Rental): string {
  return (
    reservations.find((r) => r.id === rental.reservationId)?.reference ??
    rental.reference
  )
}

export default function MyAccount() {
  const customer = useCustomerProfile()

  if (!customer) {
    return (
      <>
        <PageHeader screenId="SC-09" title="My account" />
        <SignInRequired what="your account" />
      </>
    )
  }

  const myRentals = rentals
    .filter((rental) => rental.customerId === customer.id)
    .sort((a, b) => b.collectedAt.localeCompare(a.collectedAt))
  const rentalIds = new Set(myRentals.map((rental) => rental.id))
  const myCharges = charges
    .filter((charge) => rentalIds.has(charge.rentalId))
    .sort((a, b) => b.raisedAt.localeCompare(a.raisedAt))

  const depositHeld = myRentals
    .filter((rental) => !isSettled(rental))
    .reduce((sum, rental) => sum + rental.depositHeld, 0)
  const outstanding = myCharges
    .filter(isOutstanding)
    .reduce((sum, charge) => sum + charge.amount, 0)
  const expectedBack = Math.max(0, depositHeld - outstanding)
  const lateRental = myRentals.find(
    (rental) => !isSettled(rental) && isOverdue(rental.dueBackOn),
  )

  return (
    <>
      <PageHeader
        screenId="SC-09"
        title="My account"
        subtitle={`${customer.name}, with Toolshed Hire since ${formatDate(customer.joinedOn)}.`}
        actions={
          <Link to="/reservations" className="btn-secondary px-md">
            See my hires
          </Link>
        }
      />

      {lateRental && (
        <div className="mb-lg">
          <Notice
            tone="error"
            title={`Hire ${lateRental.reference} is ${daysOverdue(lateRental.dueBackOn)} days late`}
          >
            <p>
              It was due back on {formatDate(lateRental.dueBackOn)}. The late fee
              grows every day and comes off your deposit, so returning it is the
              fastest way to stop the charge.
            </p>
          </Notice>
        </div>
      )}

      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Deposit held"
          value={money(depositHeld)}
          hint="Against hires that are still open"
        />
        <StatTile
          label="Charges to settle"
          value={money(outstanding)}
          hint="Late fees and damage, if any"
          tone={outstanding > 0 ? 'bad' : 'default'}
        />
        <StatTile
          label="Expected back"
          value={money(expectedBack)}
          hint="Once everything is returned"
          tone={expectedBack > 0 ? 'good' : 'default'}
        />
        <StatTile
          label="Hires with us"
          value={myRentals.length}
          hint={`${myRentals.filter(isSettled).length} settled in full`}
        />
      </div>

      <div className="grid gap-lg lg:grid-cols-3">
        <div className="lg:col-span-1">
          <AccountProfileCard customer={customer} />
        </div>

        <div className="flex flex-col gap-lg lg:col-span-2">
          <Card title="Hire history">
            {myRentals.length === 0 ? (
              <EmptyState
                title="No hires yet"
                body="Once you collect your first booking it will appear here, with the dates, the branch and what it cost."
                action={
                  <Link to="/" className="btn-primary px-md">
                    Browse the catalogue
                  </Link>
                }
              />
            ) : (
              <DataTable
                caption={`Hire history for ${customer.name}`}
                columns={['Hire', 'Collected', 'Due back', 'Status', 'Deposit']}
              >
                {myRentals.map((rental) => {
                  const late = !isSettled(rental) && isOverdue(rental.dueBackOn)
                  return (
                    <tr
                      key={rental.id}
                      className="transition-colors duration-200 hover:bg-muted"
                    >
                      <td className="td">
                        <p className="font-mono text-sm font-medium text-ink">
                          {rental.reference}
                        </p>
                        <p className="mt-xs text-sm text-slate-soft">
                          Booked as {referenceForRental(rental)}
                        </p>
                      </td>
                      <td className="td tabular whitespace-nowrap text-sm">
                        {formatDateShort(rental.collectedAt)}
                      </td>
                      <td className="td tabular whitespace-nowrap text-sm">
                        <span
                          className={late ? 'font-medium text-status-overdue' : ''}
                        >
                          {formatDate(rental.dueBackOn)}
                        </span>
                        {/* Colour is never the only carrier of meaning, so a
                            late date says so in words as well. */}
                        {late && (
                          <span className="block text-xs font-medium text-status-overdue">
                            Past due
                          </span>
                        )}
                      </td>
                      <td className="td">
                        <StatusPill
                          status={rental.status}
                          label={RENTAL_STATUS_LABEL[rental.status]}
                        />
                      </td>
                      <td className="td tabular whitespace-nowrap text-sm">
                        {money(rental.depositHeld)}
                      </td>
                    </tr>
                  )
                })}
              </DataTable>
            )}
          </Card>

          <Card title="Charges and refunds">
            {myCharges.length === 0 ? (
              <EmptyState
                title="Nothing charged yet"
                body="Hire charges, deposits and any late fees will be listed here as they are raised."
              />
            ) : (
              <>
                <DataTable
                  caption={`Charges raised against ${customer.name}`}
                  columns={['Raised', 'Charge', 'Against', 'Amount', 'Settled']}
                >
                  {myCharges.map((charge) => {
                    const rental = myRentals.find((r) => r.id === charge.rentalId)
                    return (
                      <tr
                        key={charge.id}
                        className="transition-colors duration-200 hover:bg-muted"
                      >
                        <td className="td tabular whitespace-nowrap text-sm">
                          {formatDateShort(charge.raisedAt)}
                        </td>
                        <td className="td">
                          <p className="text-sm font-medium text-ink">
                            {CHARGE_KIND_LABEL[charge.kind]}
                          </p>
                          <p className="mt-xs max-w-sm text-sm text-slate-soft">
                            {charge.description}
                          </p>
                        </td>
                        <td className="td font-mono text-xs text-slate-soft">
                          {rental?.reference}
                        </td>
                        <td
                          className={`td tabular whitespace-nowrap text-sm font-medium ${
                            charge.kind === 'REFUND'
                              ? 'text-status-available'
                              : 'text-ink'
                          }`}
                        >
                          {charge.kind === 'REFUND' ? '+ ' : ''}
                          {money(charge.amount)}
                        </td>
                        <td className="td">
                          {/* A charge has no status of its own in the model,
                              so the pill borrows the tone that reads right:
                              settled is green, still owing is amber. */}
                          <StatusPill
                            status={charge.settled ? 'SETTLED' : 'HELD'}
                            label={charge.settled ? 'Settled' : 'Outstanding'}
                          />
                        </td>
                      </tr>
                    )
                  })}
                </DataTable>

                <div className="mt-lg rounded-lg border border-line bg-muted p-md">
                  <h3 className="text-sm font-semibold text-ink">
                    Where your deposit stands
                  </h3>
                  <dl className="mt-sm flex flex-col gap-xs text-sm">
                    <div className="flex justify-between gap-md">
                      <dt className="text-slate-soft">Held against open hires</dt>
                      <dd className="tabular font-medium text-ink">
                        {money(depositHeld)}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-md">
                      <dt className="text-slate-soft">Charges still to settle</dt>
                      <dd className="tabular font-medium text-status-overdue">
                        minus {money(outstanding)}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-md border-t border-line pt-xs">
                      <dt className="font-medium text-ink">
                        Comes back to you on return
                      </dt>
                      <dd className="tabular font-semibold text-ink">
                        {money(expectedBack)}
                      </dd>
                    </div>
                  </dl>
                </div>
              </>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
