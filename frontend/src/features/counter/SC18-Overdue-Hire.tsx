/**
 * One overdue hire on SC-18, and the escalation queue under the list.
 *
 * A hire says who has it and how to reach them, the day it was due back, and
 * each unit still out with its days late and its late fee so far. Every one of
 * those is the server's. The days late and the late fee of a unit are
 * `daysLateToday` and `lateFeeToday`, what the late fee policy gives if it came
 * back today, so the browser adds nothing up. The hire links to its return.
 *
 * A unit more than fourteen days late is in the escalation queue, which offers
 * to record it as lost. The queue is made from the page on the screen. The
 * list is most overdue first, so the units that have waited longest are on
 * the first page.
 */

import type { Rental, RentalItem } from '../../shared/api/contract'
import { LOSS_AFTER_DAYS_LATE } from '../../shared/api/rentals'
import { formatDate, money } from '../../shared/format'
import { Card, StatusPill } from '../../shared/ui'
import { CounterEntry, EntryLink } from './counter-entry'
import { countOf } from './counter-labels'
import { rentalHref } from './counter-links'
import { itemLabel, itemsOut } from './SC15-return-model'
import { LossAction } from './SC18-Loss-Action'
import type { LossOutcome } from './SC18-Loss-Action'

/** The most days late any unit still out is, which is how late the hire is. */
function daysLate(rental: Rental): number {
  return Math.max(0, ...itemsOut(rental).map((item) => item.daysLateToday))
}

/** Whether a unit is late enough to be recorded as lost (BR-31). */
function isEscalated(item: RentalItem): boolean {
  return item.returnedAt === null && item.daysLateToday > LOSS_AFTER_DAYS_LATE
}

function UnitLine({ item }: { item: RentalItem }) {
  return (
    <li className="tabular break-words">
      <span className="font-mono">{itemLabel(item)}</span>, {item.modelName}.{' '}
      {countOf(item.daysLateToday, 'day', 'days')} late, late fee so far{' '}
      <span className="font-semibold">{money(item.lateFeeToday)}</span>.
    </li>
  )
}

export function OverdueHire({ rental }: { rental: Rental }) {
  const late = daysLate(rental)
  return (
    <CounterEntry
      reference={rental.reference}
      status={<StatusPill status="OVERDUE" label={`${countOf(late, 'day', 'days')} late`} />}
      customerName={rental.customerName}
      customerPhone={rental.customerPhone}
      actions={
        <EntryLink to={rentalHref(rental.id)} reference={rental.reference} primary>
          Take the return
        </EntryLink>
      }
    >
      <p className="tabular">Was due back {formatDate(rental.dueBackOn)}</p>
      <ul aria-label={`Units still out on ${rental.reference}`} className="flex flex-col gap-xs">
        {itemsOut(rental).map((item) => (
          <UnitLine key={item.id} item={item} />
        ))}
      </ul>
    </CounterEntry>
  )
}

export function EscalationQueue({
  hires,
  onRecorded,
}: {
  hires: readonly Rental[]
  onRecorded: (outcome: LossOutcome) => void
}) {
  const escalated = hires.flatMap((rental) =>
    rental.items.filter(isEscalated).map((item) => ({ rental, item })),
  )
  return (
    <Card title={`Escalation queue, more than ${LOSS_AFTER_DAYS_LATE} days late`}>
      <p className="mb-md text-sm text-slate-soft">
        A unit more than {LOSS_AFTER_DAYS_LATE} days past its due date can be recorded as lost, and the hire goes to
        the owner for recovery. Ring the customer first.
      </p>
      {escalated.length === 0 ? (
        <p className="text-sm text-slate-soft">
          Nothing on this page is more than {LOSS_AFTER_DAYS_LATE} days late.
        </p>
      ) : (
        <ul aria-label="Units in the escalation queue">
          {escalated.map(({ rental, item }) => (
            <CounterEntry
              key={item.id}
              reference={`${itemLabel(item)} on ${rental.reference}`}
              status={<StatusPill status="OVERDUE" label={`${countOf(item.daysLateToday, 'day', 'days')} late`} />}
              customerName={rental.customerName}
              customerPhone={rental.customerPhone}
              footer={<LossAction rental={rental} item={item} onRecorded={onRecorded} />}
            >
              <p className="tabular">
                {item.modelName}. Late fee so far <span className="font-semibold">{money(item.lateFeeToday)}</span>.
              </p>
            </CounterEntry>
          ))}
        </ul>
      )}
    </Card>
  )
}
