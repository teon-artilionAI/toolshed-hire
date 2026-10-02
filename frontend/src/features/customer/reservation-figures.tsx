/**
 * What is on a reservation and what it costs, on SC-04 and SC-08.
 *
 * Every figure here is the server's. The reservation routes send the rates
 * each line was priced at, what each line comes to, the subtotal, the VAT, the
 * total and the deposit, and these components write out what was sent. Nothing
 * is added, multiplied or rounded in the browser. The dates, the count of days
 * and the name of the branch are the server's too.
 *
 * The deposit is never rolled into the total. It is held when the equipment is
 * collected and returned afterwards, so it is shown apart and says so.
 */

import type { Reservation } from '../../shared/api/contract'
import { formatDate, money, percent } from '../../shared/format'
import { Card, DataTable } from '../../shared/ui'

/** The sentence that goes with every deposit figure. */
export const DEPOSIT_SENTENCE =
  'The deposit is held when you collect the equipment and returned to you after you bring it back.'

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

/** Whether a percentage the API sent is nothing at all, for example "0.00". */
function isNoPercent(rate: string): boolean {
  return Number(rate) === 0
}

/** Every line of a reservation. The rates sit under the name and not in
 *  columns of their own, so the table still fits a phone held in one hand. */
export function ReservationLines({ reservation }: { reservation: Reservation }) {
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
              {money(line.weeklyRate)} a week
            </span>
            <span className="tabular mt-xs block text-sm text-slate-soft">
              {money(line.depositPerUnit)} deposit each
            </span>
          </td>
          <td className="td tabular whitespace-nowrap text-right font-medium">
            {money(line.lineSubtotalExVat)}
          </td>
        </tr>
      ))}
    </DataTable>
  )
}

/** The subtotal, the VAT and the total, then the deposit apart from them. */
export function ReservationTotals({ reservation }: { reservation: Reservation }) {
  const discounted = !isNoPercent(reservation.discountPercent)
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
          Priced with your discount of {percent(reservation.discountPercent)}.
        </p>
      )}
      <dl className="mt-md border-t border-line pt-md">
        <Figure term="Deposit" amount={money(reservation.depositTotal)} />
      </dl>
      <p className="mt-xs text-sm text-slate-soft">{DEPOSIT_SENTENCE}</p>
    </>
  )
}

/** The dates and the branch of a reservation, as the server holds them. */
export function ReservationTermsCard({ reservation }: { reservation: Reservation }) {
  return (
    <Card title="When and where">
      <dl className="grid gap-md text-sm sm:grid-cols-2">
        <div>
          <dt className="font-medium text-ink">Hire period</dt>
          <dd className="tabular mt-xs text-slate-soft">
            {formatDate(reservation.from)} to {formatDate(reservation.to)}, {reservation.hireDays}{' '}
            {reservation.hireDays === 1 ? 'day' : 'days'}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-ink">Collect from</dt>
          <dd className="mt-xs text-slate-soft">{reservation.branchName}</dd>
        </div>
      </dl>
    </Card>
  )
}

/** One figure and what it is. A figure such as R 4 508,00 holds a space, so it
 *  is kept on one line. A price split across two lines reads as two numbers. */
function Figure({ term, amount, strong = false }: { term: string; amount: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-md">
      <dt className={strong ? 'text-base font-semibold text-ink' : 'text-sm text-slate-soft'}>
        {term}
      </dt>
      <dd
        className={`tabular whitespace-nowrap ${
          strong ? 'text-xl font-semibold text-ink' : 'text-sm text-ink'
        }`}
      >
        {amount}
      </dd>
    </div>
  )
}
