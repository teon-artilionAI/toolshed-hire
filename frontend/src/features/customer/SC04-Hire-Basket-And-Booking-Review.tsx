/**
 * SC-04 Hire Basket and Booking Review.
 *
 * The last screen before money changes hands, so it shows its working. Every
 * line spells out quantity times days times rate, the deposit is separated
 * from the hire charge because one comes back and the other does not, and
 * the late fee is stated before the customer agrees rather than after.
 *
 * A booking that cannot be made says why and offers the fix. The basket
 * carries one collection branch and one period for the whole hire, which is
 * exactly what a Reservation holds in the domain model.
 */

import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CircleCheck, ShoppingCart } from 'lucide-react'
import { branches } from '../../shared/fixtures'
import type { BranchCode, Uuid } from '../../shared/types'
import { formatDate, money } from '../../shared/format'
import { useSession } from '../../shared/session'
import { Card, DataTable, EmptyState, Notice, PageHeader } from '../../shared/ui'
import { availabilityAt } from './availability'
import { DEFAULT_END, DEFAULT_START, validatePeriod } from './hire-period'
import { hireDays, modelById } from './catalogue-data'
import { BranchSelect, PeriodFields } from './catalogue-ui'
import BasketConfirmed from './basket-confirmed'
import { readBranch } from './branch-params'
import BasketLine from './basket-line'
import type { BasketItem } from './basket-state'
import { nextReference, seedBasket } from './basket-state'
import BasketTotals from './basket-totals'

export default function Basket() {
  const [params] = useSearchParams()
  const { setBasketCount } = useSession()

  const [lines, setLines] = useState<BasketItem[]>(() =>
    seedBasket(params.get('add'), Math.max(1, Number.parseInt(params.get('qty') ?? '1', 10) || 1)),
  )
  const [startIso, setStartIso] = useState(params.get('from') ?? DEFAULT_START)
  const [endIso, setEndIso] = useState(params.get('to') ?? DEFAULT_END)
  const [branchCode, setBranchCode] = useState<BranchCode>(readBranch(params.get('branch')))
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [confirmedReference, setConfirmedReference] = useState<string | null>(null)

  const periodError = validatePeriod(startIso, endIso)
  const usablePeriod = periodError === null
  const days = hireDays(startIso, endIso)

  const priced = useMemo(
    () =>
      lines.flatMap((line) => {
        const model = modelById(line.modelId)
        if (!model) return []
        const availability = usablePeriod
          ? availabilityAt(model.id, branchCode, startIso, endIso)
          : null
        return [
          {
            line,
            model,
            availability,
            hire: line.quantity * days * model.dailyRate,
            deposit: line.quantity * model.depositAmount,
            short: availability !== null && line.quantity > availability.availableUnits,
          },
        ]
      }),
    [lines, branchCode, startIso, endIso, days, usablePeriod],
  )

  const hireTotal = priced.reduce((sum, row) => sum + row.hire, 0)
  const depositTotal = priced.reduce((sum, row) => sum + row.deposit, 0)
  const itemCount = lines.reduce((sum, line) => sum + line.quantity, 0)
  const blocked = priced.filter((row) => row.short)

  /** A branch that could take the whole booking as it stands. */
  const rescueBranch = useMemo(() => {
    if (!usablePeriod || blocked.length === 0) return null
    return (
      branches.find(
        (b) =>
          b.code !== branchCode &&
          lines.every((line) => {
            const model = modelById(line.modelId)
            if (!model) return true
            return availabilityAt(model.id, b.code, startIso, endIso).availableUnits >= line.quantity
          }),
      ) ?? null
    )
  }, [blocked.length, branchCode, lines, startIso, endIso, usablePeriod])

  useEffect(() => setBasketCount(itemCount), [itemCount, setBasketCount])

  const collectionBranch =
    branches.find((b) => b.code === branchCode) ?? branches[0]

  const readyToConfirm =
    usablePeriod && lines.length > 0 && blocked.length === 0 && termsAccepted

  function setQuantity(modelId: Uuid, quantity: number) {
    setLines((current) =>
      current.map((line) => (line.modelId === modelId ? { ...line, quantity } : line)),
    )
  }

  function removeLine(modelId: Uuid) {
    setLines((current) => current.filter((line) => line.modelId !== modelId))
  }

  if (confirmedReference) {
    return (
      <BasketConfirmed
        reference={confirmedReference}
        branch={collectionBranch}
        startIso={startIso}
        itemCount={itemCount}
        hireTotal={hireTotal}
        depositTotal={depositTotal}
        days={days}
      />
    )
  }

  return (
    <>
      <PageHeader
        screenId="SC-04"
        title="Your hire basket"
        subtitle="Check the dates, the branch and the arithmetic before you confirm. Nothing is charged until you collect."
      />

      {lines.length === 0 ? (
        <div className="card">
          <EmptyState
            title="Your basket is empty"
            body="Pick your dates on the catalogue and add the tools you need. We will hold them for the whole period."
            action={
              <Link to="/" className="btn-primary px-lg">
                <ShoppingCart className="h-4 w-4 shrink-0" aria-hidden="true" />
                Browse the catalogue
              </Link>
            }
          />
        </div>
      ) : (
        <div className="grid gap-lg lg:grid-cols-5">
          <div className="flex min-w-0 flex-col gap-lg lg:col-span-3">
            <Card title="When and where">
              <div className="grid gap-md sm:grid-cols-3">
                <PeriodFields
                  idPrefix="basket"
                  startIso={startIso}
                  endIso={endIso}
                  onChangeStart={setStartIso}
                  onChangeEnd={setEndIso}
                  error={periodError}
                />
                <BranchSelect
                  id="basket-branch"
                  value={branchCode}
                  onChange={(value) => setBranchCode(value as BranchCode)}
                />
              </div>
              <p className="mt-md text-sm text-slate-soft">
                {days} {days === 1 ? 'day' : 'days'}, {formatDate(startIso)} to{' '}
                {formatDate(endIso)}. You are charged to the morning you bring it back.
              </p>
            </Card>

            {blocked.length > 0 && (
              <Notice
                tone="error"
                title={
                  blocked.length === 1
                    ? 'One item in your basket is not free at this branch'
                    : `${blocked.length} items in your basket are not free at this branch`
                }
              >
                <p>
                  Each line below says what is in the way. Reduce the quantity, move your dates,
                  or collect from a branch that has the stock.
                </p>
                {rescueBranch && (
                  <button
                    type="button"
                    className="btn-secondary mt-sm px-md"
                    onClick={() => setBranchCode(rescueBranch.code)}
                  >
                    {rescueBranch.name} can supply the whole basket, move it there
                  </button>
                )}
              </Notice>
            )}

            <Card title={`What you are hiring, ${itemCount} ${itemCount === 1 ? 'item' : 'items'}`}>
              <ul className="flex flex-col gap-lg">
                {priced.map(({ line, model, availability, hire, short }) => (
                  <BasketLine
                    key={model.id}
                    model={model}
                    quantity={line.quantity}
                    days={days}
                    hire={hire}
                    availability={availability}
                    short={short}
                    branchCode={branchCode}
                    startIso={startIso}
                    endIso={endIso}
                    onChangeQuantity={setQuantity}
                    onRemove={removeLine}
                  />
                ))}
              </ul>
            </Card>
          </div>

          <div className="min-w-0 lg:col-span-2 lg:sticky lg:top-24 lg:self-start">
            <Card title="The arithmetic">
              {/* The working sits under the item name rather than in its own
                  column, so the sum still fits on a 375px phone without the
                  amount sliding out of sight. */}
              <DataTable
                columns={['Item and working', 'Hire charge']}
                caption="How the hire charge was reached, line by line"
              >
                {priced.map(({ model, line, hire }) => (
                  <tr key={model.id}>
                    <td className="td">
                      <span className="block font-medium text-ink">{model.name}</span>
                      <span className="tabular mt-xs block text-xs text-slate-soft">
                        {line.quantity} × {days} {days === 1 ? 'day' : 'days'} ×{' '}
                        {money(model.dailyRate)}
                      </span>
                    </td>
                    <td className="td tabular whitespace-nowrap text-right font-medium">
                      {money(hire)}
                    </td>
                  </tr>
                ))}
              </DataTable>
              <div className="mt-md">
                <BasketTotals hireTotal={hireTotal} depositTotal={depositTotal} days={days} />
              </div>

              <p className="mt-md rounded bg-muted p-md text-sm text-slate-soft">
                Bring it back late and the late fee for each tool applies for every day it is
                out, taken off the deposit.
              </p>

              <div className="mt-md">
                <label className="flex min-h-[2.75rem] cursor-pointer items-start gap-sm py-sm text-sm text-ink">
                  <input
                    type="checkbox"
                    className="h-6 w-6 shrink-0 cursor-pointer accent-accent"
                    checked={termsAccepted}
                    onChange={(e) => setTermsAccepted(e.target.checked)}
                    aria-describedby="terms-help"
                  />
                  <span id="terms-help">
                    I accept the hire terms, the deposit and the late fee shown above.
                  </span>
                </label>
                {submitted && !termsAccepted && (
                  <p className="field-error">
                    <span>Tick the box to accept the hire terms before you confirm.</span>
                  </p>
                )}
              </div>

              <button
                type="button"
                className="btn-primary mt-md w-full"
                onClick={() => {
                  setSubmitted(true)
                  if (readyToConfirm) setConfirmedReference(nextReference())
                }}
                disabled={blocked.length > 0 || !usablePeriod}
              >
                <CircleCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                Confirm this hire
              </button>
              <p className="mt-sm text-center text-sm text-slate-soft">
                You pay at the counter when you collect.
              </p>
            </Card>
          </div>
        </div>
      )}
    </>
  )
}
