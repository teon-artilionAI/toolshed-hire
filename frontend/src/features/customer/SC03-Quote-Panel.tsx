/**
 * The price on the "Book this tool" card of SC-03.
 *
 * Every figure here is the server's. The quote route prices the dates and the
 * quantity the customer chose, and this panel writes out what it sent. Nothing
 * is added, multiplied or rounded in the browser, so the figure a customer
 * reads here is the figure a booking will charge.
 *
 * The total is the hire charge with VAT. The deposit is not part of it and is
 * shown apart from it, because a deposit is held and returned and not charged.
 *
 * The quote is asked for again every time a date or the quantity changes, and
 * the old one is never left on the page while the new one is on its way. A
 * price for two units beside a stepper that says three would be a wrong price.
 */

import type { UseQueryResult } from '@tanstack/react-query'
import type { ModelQuote } from '../../shared/api/contract'
import { isRefusal } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { isNoMoney, money, percent } from '../../shared/format'

/** The id of the heading the panel is named by. */
const HEADING_ID = 'detail-quote-heading'

/** Two skeleton blocks stand about as tall as the price and the deposit under
 *  it, so the basket button does not jump when the quote lands. */
const PRICE_SKELETON_BLOCKS = 2

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

/**
 * How long one unit is charged for, in the words a counter would use.
 *
 * On the weekly basis the hire is whole weeks and the days left over. On the
 * daily basis every day of the hire is charged at the daily rate.
 */
function chargedFor(quote: ModelQuote): string {
  const { basis, wholeWeeks, remainderDays } = quote.perUnit
  if (basis === 'daily') return `${plural(quote.hireDays, 'day', 'days')} at the daily rate`
  const weeks = plural(wholeWeeks, 'week', 'weeks')
  return remainderDays === 0
    ? `${weeks} at the weekly rate`
    : `${weeks} and ${plural(remainderDays, 'day', 'days')}`
}

/** The rates behind the charge, and what one unit comes to when there are several. */
function ratesBehind(quote: ModelQuote): string {
  const { basis, remainderDays, dailyRate, weeklyRate, amountExVat } = quote.perUnit
  const daily = `${money(dailyRate)} a day`
  const weekly = `${money(weeklyRate)} a week`
  const rates =
    basis === 'daily' ? daily : remainderDays === 0 ? weekly : `${weekly} and ${daily}`
  return quote.quantity === 1
    ? `${rates}.`
    : `${rates}, which is ${money(amountExVat)} for each unit before VAT.`
}

export default function QuotePanel({ quote }: { quote: UseQueryResult<ModelQuote> }) {
  const phase = queryPhase(quote)
  // A refusal is about the dates or the quantity. The card puts each message
  // under its field, so the panel only says why there is no price.
  const refused = phase === 'failed' && isRefusal(quote.error)

  if (phase === 'loading') {
    return (
      <LoadingState label="Working out the price" shape="rows" count={PRICE_SKELETON_BLOCKS} />
    )
  }

  if (phase === 'failed' && !refused) {
    return (
      <ErrorState
        what="the price for these dates"
        error={quote.error}
        onRetry={() => void quote.refetch()}
      />
    )
  }

  if (phase !== 'ready' || !quote.data) {
    return (
      <p className="rounded bg-muted p-md text-sm text-slate-soft">
        {refused
          ? 'The price shows here once the details above are accepted.'
          : 'Choose your dates to see the price.'}
      </p>
    )
  }

  const price = quote.data
  const discounted = !isNoMoney(price.discountAmount)

  return (
    <div
      role="group"
      aria-labelledby={HEADING_ID}
      aria-busy={quote.isFetching}
      className="rounded bg-muted p-md"
    >
      <h3 id={HEADING_ID} className="text-sm font-semibold text-ink">
        Price for these dates
      </h3>
      <p className="mt-xs text-sm text-ink">
        {price.quantity === 1
          ? chargedFor(price)
          : `${price.quantity} units, each for ${chargedFor(price)}`}
      </p>
      <p className="tabular mt-xs text-sm text-slate-soft">{ratesBehind(price)}</p>

      <dl className="mt-md grid gap-xs">
        <Line term="Hire before VAT" amount={money(price.subtotalExVat)} />
        {discounted && (
          <Line
            term={`Discount of ${percent(price.discountPercent)}`}
            amount={money(`-${price.discountAmount}`)}
          />
        )}
        <Line term={`VAT at ${percent(price.vatRate)}`} amount={money(price.vatAmount)} />
        <Line term="Total with VAT" amount={money(price.totalIncVat)} strong />
      </dl>

      <dl className="mt-md border-t border-line pt-md">
        <Line term="Deposit" amount={money(price.depositTotal)} />
      </dl>
      <p className="mt-xs text-sm text-slate-soft">
        The deposit is held when you collect the equipment and returned to you after you bring
        it back.
      </p>
      <p className="tabular mt-sm text-sm text-slate-soft">
        Late fee of {money(price.lateFeePerDay)} per day past the return date.
      </p>
    </div>
  )
}

/** One figure and what it is. A figure such as R 4 508,00 holds a space, so it
 *  is kept on one line. A price split across two lines reads as two numbers. */
function Line({ term, amount, strong = false }: { term: string; amount: string; strong?: boolean }) {
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
