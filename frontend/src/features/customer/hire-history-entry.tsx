/**
 * One hire in the history on SC-09.
 *
 * The reference, the branch, the dates and the status in words, then what was
 * hired, every charge, and where the deposit stands. Every figure is the
 * server's. The models are named and counted, and no tag or serial number is
 * ever shown, because a customer is never given one and the server sends none.
 *
 * A deposit given back is a negative amount on the wire. It is written as
 * returned to the customer, never with a bare minus sign.
 */

import type { Rental, RentalCharge } from '../../shared/api/contract'
import { formatDate, isNegativeMoney, money, unsignedMoney } from '../../shared/format'
import { branchDateTime } from '../../shared/today'
import { StatusPill } from '../../shared/ui'
import { HIRE_CHARGE_LABEL, HIRE_CHARGE_STATUS_LABEL, HIRE_STATUS_LABEL } from './customer-labels'

/** What was hired, by model, for example "2 x CP 100 Plate Compactor". */
function modelsHired(rental: Rental): string {
  const counts = new Map<string, number>()
  for (const item of rental.items) counts.set(item.modelName, (counts.get(item.modelName) ?? 0) + 1)
  return [...counts].map(([name, count]) => `${count} x ${name}`).join(', ')
}

/** When the hire ran, in one line. */
function datesOf(rental: Rental): string {
  const out = `Collected ${formatDate(rental.from)}, due back ${formatDate(rental.dueBackOn)}.`
  return rental.returnedAt === null ? out : `${out} Returned ${branchDateTime(rental.returnedAt)}.`
}

/** An amount in words that say which way it runs. */
function amountInWords(amount: string): string {
  return isNegativeMoney(amount) ? `${unsignedMoney(amount)} returned to you` : money(amount)
}

function ChargeLine({ charge }: { charge: RentalCharge }) {
  return (
    <li className="flex flex-wrap justify-between gap-x-md gap-y-xs border-b border-line py-xs last:border-0">
      <span className="min-w-0 break-words text-ink">
        {HIRE_CHARGE_LABEL[charge.type]}. {charge.description}
        <span className="block text-xs text-slate-soft">{HIRE_CHARGE_STATUS_LABEL[charge.status]}</span>
      </span>
      <span className="tabular whitespace-nowrap font-medium text-ink">{amountInWords(charge.amountIncVat)}</span>
    </li>
  )
}

function DepositLine({ term, amount }: { term: string; amount: string }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-md">
      <dt className="text-slate-soft">{term}</dt>
      <dd className="tabular font-medium text-ink">{money(amount)}</dd>
    </div>
  )
}

export function HireHistoryEntry({ rental }: { rental: Rental }) {
  const headingId = `hire-${rental.id}`
  return (
    <li className="border-t border-line py-md first:border-t-0 first:pt-0">
      <article aria-labelledby={headingId}>
        <div className="flex flex-wrap items-center justify-between gap-sm">
          <h3 id={headingId} className="font-mono text-sm font-semibold text-ink">
            {rental.reference}
          </h3>
          <StatusPill status={rental.status} label={HIRE_STATUS_LABEL[rental.status]} />
        </div>
        <p className="mt-xs text-sm text-ink">From {rental.branchName}</p>
        <p className="tabular text-sm text-slate-soft">{datesOf(rental)}</p>
        <p className="mt-xs break-words text-sm text-ink">{modelsHired(rental)}</p>

        <h4 className="mt-md text-xs font-semibold uppercase tracking-wide text-slate-soft">Charges</h4>
        {rental.charges.length === 0 ? (
          <p className="text-sm text-slate-soft">No charges on this hire.</p>
        ) : (
          <ul className="text-sm">
            {rental.charges.map((charge) => (
              <ChargeLine key={charge.id} charge={charge} />
            ))}
          </ul>
        )}

        <h4 className="mt-md text-xs font-semibold uppercase tracking-wide text-slate-soft">Your deposit</h4>
        <dl className="mt-xs grid gap-xs text-sm">
          <DepositLine term="Held" amount={rental.depositHeld} />
          <DepositLine term="Kept for charges" amount={rental.depositWithheld} />
          <DepositLine term="Returned to you" amount={rental.depositRefunded} />
          <DepositLine term="Balance due" amount={rental.balanceDue} />
        </dl>
      </article>
    </li>
  )
}
