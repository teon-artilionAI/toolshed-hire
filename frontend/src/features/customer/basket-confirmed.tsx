/**
 * The confirmation SC-04 shows once a hire has been booked.
 *
 * It repeats the figures rather than assuming the customer remembers them,
 * names the branch and the day, and says what to bring. A confirmation that
 * only says "thank you" leaves the customer ringing the branch to ask what
 * happens next.
 */

import { Link } from 'react-router-dom'
import type { Branch } from '../../shared/types'
import { formatDate } from '../../shared/format'
import { Card, Notice, PageHeader } from '../../shared/ui'
import BasketTotals from './basket-totals'

export default function BasketConfirmed({
  reference,
  branch,
  startIso,
  itemCount,
  hireTotal,
  depositTotal,
  days,
}: {
  reference: string
  branch: Branch
  startIso: string
  itemCount: number
  hireTotal: number
  depositTotal: number
  days: number
}) {
  return (
    <>
      <PageHeader
        screenId="SC-04"
        title="Your hire is booked"
        subtitle={`Collect from ${branch.name} on ${formatDate(startIso)}.`}
      />
      <Notice tone="success" title={`Booking ${reference} is confirmed`}>
        <p>
          We have emailed the confirmation and held {itemCount}{' '}
          {itemCount === 1 ? 'item' : 'items'} for you. Bring the card you are paying with and
          your ID when you collect.
        </p>
      </Notice>
      <Card title="What you owe at the counter" className="mt-lg">
        <BasketTotals hireTotal={hireTotal} depositTotal={depositTotal} days={days} />
        <div className="mt-lg flex flex-wrap gap-sm">
          <Link to="/reservations" className="btn-primary px-lg">
            See my hires
          </Link>
          <Link to="/" className="btn-secondary px-lg">
            Hire something else
          </Link>
        </div>
      </Card>
    </>
  )
}
