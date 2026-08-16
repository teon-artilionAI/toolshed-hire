/**
 * What SC-13 shows once the booking is made.
 *
 * The reference, the units actually set aside, and the money the customer
 * will hand over at the counter. A counter assistant reads this back to
 * the customer, so it is written to be read out loud.
 */

import { Link } from 'react-router-dom'
import { Card, Notice, PageHeader } from '../../shared/ui'
import { formatDate, money } from '../../shared/format'
import type { BranchCode, CustomerProfile } from '../../shared/types'
import { branchByCode, modelById } from './counter-desk-data'
import type { BookingLineDraft, LineAllocation } from './counter-availability'

export default function BookingConfirmed({
  reference,
  customer,
  branchCode,
  startDate,
  endDate,
  lines,
  allocations,
  hireTotal,
  depositTotal,
  onStartAnother,
}: {
  reference: string
  customer: CustomerProfile
  branchCode: BranchCode
  startDate: string
  endDate: string
  lines: BookingLineDraft[]
  allocations: LineAllocation[]
  hireTotal: number
  depositTotal: number
  onStartAnother: () => void
}) {
  return (
    <div>
      <PageHeader
        screenId="SC-13"
        title="Booking confirmed"
        subtitle={`Reference ${reference}.`}
      />
      <Notice tone="success" title={`${reference} is on the diary`}>
        <p>
          {customer.name}, collecting from {branchByCode(branchCode).name} on{' '}
          {formatDate(startDate)} and back on {formatDate(endDate)}.{' '}
          {customer.email
            ? `A confirmation has been emailed to ${customer.email}.`
            : `No email on file, so the confirmation goes by text to ${customer.phone}.`}
        </p>
      </Notice>

      <Card title="What was set aside" className="mt-lg">
        <ul className="flex flex-col gap-sm">
          {lines.map((line, index) => (
            <li key={line.id} className="flex flex-wrap items-center gap-sm text-sm">
              <span className="font-medium text-ink">
                {line.quantity} x {modelById(line.modelId).name}
              </span>
              <span className="font-mono text-slate-soft">
                {allocations[index].chosen.map((unit) => unit.asset.tag).join(', ')}
              </span>
            </li>
          ))}
        </ul>
        <p className="tabular mt-md text-sm text-slate-soft">
          Hire {money(hireTotal)}, deposit {money(depositTotal)} held on collection.
        </p>
        <div className="mt-lg flex flex-wrap gap-sm">
          <button type="button" className="btn-primary" onClick={onStartAnother}>
            Start another booking
          </button>
          <Link to="/counter/diary" className="btn-secondary">
            Open the diary
          </Link>
        </div>
      </Card>
    </div>
  )
}
