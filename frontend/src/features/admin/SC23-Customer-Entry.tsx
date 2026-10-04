/**
 * One customer in the customer holds on SC-23.
 *
 * The name, the company of a trade account, where the customer stands in words
 * beside its colour, how many bookings they did not collect, how to reach
 * them and their home branch, every value as the server sent it. Below them
 * are the moves of the customer's standing, which are the standings the
 * customer is not in. "Release the hold" moves a customer on hold back to good
 * standing, "Put on hold" stops new bookings, and "Blacklist" stops them at
 * every branch. Each opens its question in place of the buttons, and putting
 * the question away gives focus back to the button that opened it.
 */

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { AccountStatus, CustomerSummary } from '../../shared/api/contract'
import { StatusPill } from '../../shared/ui'
import { ACCOUNT_STANDING_LABEL, ACCOUNT_STANDING_PILL, CUSTOMER_TYPE_LABEL } from '../counter/counter-labels'
import { StandingQuestion } from './SC23-Standing-Question'
import { noShowWords, standingMoveWords, standingMoves } from './staff-words'

function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-soft">{term}</dt>
      <dd className="mt-xs break-words text-sm text-ink">{children}</dd>
    </div>
  )
}

export function CustomerEntry({
  customer,
  branchName,
  onMoved,
}: {
  customer: CustomerSummary
  branchName: (code: string) => string
  /** Called with the customer the server answered with, and the standing asked for. */
  onMoved: (customer: CustomerSummary, to: AccountStatus) => void
}) {
  const [asking, setAsking] = useState<AccountStatus | null>(null)
  const buttons = useRef(new Map<AccountStatus, HTMLButtonElement>())
  // The move whose question was put away unanswered, so focus can go back to
  // its button once that button is on the page again.
  const putAway = useRef<AccountStatus | null>(null)
  const headingId = `customer-${customer.id}-name`

  useEffect(() => {
    if (asking !== null || putAway.current === null) return
    buttons.current.get(putAway.current)?.focus()
    putAway.current = null
  }, [asking])

  return (
    <article aria-labelledby={headingId} className="card min-w-0 p-lg">
      <h3 id={headingId} className="break-words text-base font-semibold text-ink">
        {customer.displayName}
      </h3>
      {customer.companyName !== null && <p className="break-words text-sm text-slate-soft">{customer.companyName}</p>}
      <dl className="mt-md grid gap-md sm:grid-cols-2 lg:grid-cols-3">
        <Fact term="Standing">
          <StatusPill status={ACCOUNT_STANDING_PILL[customer.accountStatus]} label={ACCOUNT_STANDING_LABEL[customer.accountStatus]} />
        </Fact>
        <Fact term="Bookings not collected">{noShowWords(customer)}</Fact>
        <Fact term="Customer type">{CUSTOMER_TYPE_LABEL[customer.customerType]}</Fact>
        <Fact term="Email">
          <span className="break-all">{customer.email ?? 'No online account'}</span>
        </Fact>
        <Fact term="Phone">{customer.phone}</Fact>
        <Fact term="Home branch">{branchName(customer.homeBranchCode)}</Fact>
      </dl>
      <div className="mt-md">
        {asking !== null ? (
          <StandingQuestion
            key={asking}
            customer={customer}
            to={asking}
            onMoved={(moved) => {
              const to = asking
              setAsking(null)
              onMoved(moved, to)
            }}
            onCancel={() => {
              putAway.current = asking
              setAsking(null)
            }}
          />
        ) : (
          <ul className="flex flex-wrap gap-sm" aria-label={`What can be done with the account of ${customer.displayName}`}>
            {standingMoves(customer).map((to) => (
              <li key={to}>
                <button
                  ref={(button) => {
                    if (button === null) buttons.current.delete(to)
                    else buttons.current.set(to, button)
                  }}
                  type="button"
                  className={to === 'BLACKLISTED' ? 'btn-danger px-md' : 'btn-secondary px-md'}
                  onClick={() => setAsking(to)}
                >
                  {standingMoveWords(customer, to).action}
                  <span className="sr-only"> for {customer.displayName}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  )
}
