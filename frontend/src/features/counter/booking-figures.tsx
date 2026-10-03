/**
 * What is on a counter booking and what it costs, on SC-13.
 *
 * Every figure here is the server's. The reservation routes send the rates
 * each line was priced at, what each line comes to, the subtotal, the VAT, the
 * total and the deposit, and these components write out what was sent. Nothing
 * is added, multiplied or rounded in the browser.
 *
 * Staff see the asset tags of the units set aside once the equipment is held,
 * so the assistant can read them back and fetch the right units. The deposit is
 * shown apart from the total, because it is taken at collection and given back
 * at the return.
 */

import type { Reservation } from '../../shared/api/contract'
import { money, percent } from '../../shared/format'
import { DataTable } from '../../shared/ui'

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

/** Every line of a reservation, with its rates and, once held, its units. */
export function BookingLines({ reservation }: { reservation: Reservation }) {
  return (
    <DataTable
      columns={['Equipment', 'Hire before VAT']}
      caption={`What is on booking ${reservation.reference}, line by line`}
    >
      {reservation.lines.map((line) => (
        <tr key={line.modelSlug}>
          <td className="td">
            <span className="block font-medium text-ink">{line.modelName}</span>
            <span className="tabular mt-xs block text-sm text-slate-soft">
              {plural(line.quantity, 'unit', 'units')}, {money(line.dailyRate)} a day or{' '}
              {money(line.weeklyRate)} a week, {money(line.depositPerUnit)} deposit each
            </span>
            {line.assetTags.length > 0 && (
              <span className="mt-xs block text-sm text-ink">
                Set aside: <span className="break-all font-mono">{line.assetTags.join(', ')}</span>
              </span>
            )}
          </td>
          <td className="td tabular whitespace-nowrap text-right font-medium">
            {money(line.lineSubtotalExVat)}
          </td>
        </tr>
      ))}
    </DataTable>
  )
}

/** One figure and what it is, kept on one line so a price never reads as two numbers. */
function Figure({ term, amount, strong = false }: { term: string; amount: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-md">
      <dt className={strong ? 'text-base font-semibold text-ink' : 'text-sm text-slate-soft'}>{term}</dt>
      <dd
        className={`tabular whitespace-nowrap ${strong ? 'text-xl font-semibold text-ink' : 'text-sm text-ink'}`}
      >
        {amount}
      </dd>
    </div>
  )
}

/** The subtotal, the VAT and the total, then the deposit to take apart from them. */
export function BookingTotals({ reservation }: { reservation: Reservation }) {
  const discounted = Number(reservation.discountPercent) !== 0
  return (
    <>
      <dl className="grid gap-xs">
        <Figure
          term={`Hire before VAT, ${plural(reservation.hireDays, 'day', 'days')}`}
          amount={money(reservation.subtotalExVat)}
        />
        <Figure term="VAT" amount={money(reservation.vatAmount)} />
        <Figure term="Total with VAT" amount={money(reservation.estimatedTotalIncVat)} strong />
      </dl>
      {discounted && (
        <p className="tabular mt-xs text-sm text-slate-soft">
          Priced with the trade discount of {percent(reservation.discountPercent)}.
        </p>
      )}
      <dl className="mt-md border-t border-line pt-md">
        <Figure term="Deposit to take at collection" amount={money(reservation.depositTotal)} strong />
      </dl>
      <p className="mt-xs text-sm text-slate-soft">
        The deposit is held when the equipment goes out and given back at the return, less anything
        owed.
      </p>
    </>
  )
}
