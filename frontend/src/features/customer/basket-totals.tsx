/**
 * What the hire adds up to, on SC-04.
 *
 * The hire charge and the deposit are shown as separate figures because one
 * is spent and the other comes back. Rolling them into a single "total"
 * would be the shortest way to make a customer feel misled at the counter.
 */

import { Receipt } from 'lucide-react'
import { money } from '../../shared/format'

function TotalsRow({ term, detail }: { term: string; detail: string }) {
  return (
    <div className="flex items-baseline justify-between gap-md">
      <dt className="text-slate-soft">{term}</dt>
      <dd className="tabular font-medium text-ink">{detail}</dd>
    </div>
  )
}

export default function BasketTotals({
  hireTotal,
  depositTotal,
  days,
}: {
  hireTotal: number
  depositTotal: number
  days: number
}) {
  return (
    <dl className="flex flex-col gap-sm text-sm">
      <TotalsRow
        term={`Hire charge, ${days} ${days === 1 ? 'day' : 'days'}`}
        detail={money(hireTotal)}
      />
      <TotalsRow term="Refundable deposit" detail={money(depositTotal)} />
      <div className="flex items-baseline justify-between gap-md border-t border-line pt-sm">
        <dt className="flex items-center gap-sm text-base font-semibold text-ink">
          <Receipt className="h-4 w-4 shrink-0" aria-hidden="true" />
          Due at collection
        </dt>
        <dd className="tabular text-xl font-semibold text-ink">
          {money(hireTotal + depositTotal)}
        </dd>
      </div>
    </dl>
  )
}
