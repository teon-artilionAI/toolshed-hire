/**
 * The "Book this tool" card on SC-03.
 *
 * The customer picks dates, a branch and a quantity, and the card says whether
 * that branch can supply that many for the whole period. The answer is the
 * API's, asked again every time one of the three changes. It is free or not
 * free, never a count.
 *
 * The API is the judge of the dates and the quantity. What it refuses comes
 * back as a 422 and each message is shown under the field it is about.
 */

import { Link } from 'react-router-dom'
import type { UseQueryResult } from '@tanstack/react-query'
import { ShoppingCart } from 'lucide-react'
import { MAX_QUANTITY, MIN_QUANTITY } from '../../shared/api/catalogue'
import type { BranchList, ModelAvailability, ModelDetail } from '../../shared/api/contract'
import {
  HTTP_UNPROCESSABLE,
  fieldErrorsFromProblem,
  otherFieldMessages,
} from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { isApiError } from '../../shared/api-problem'
import { ErrorState } from '../../shared/async-states'
import { money, moneyTimes } from '../../shared/format'
import { Card, Notice, StatusPill } from '../../shared/ui'
import { ANY_BRANCH, BranchSelect, PeriodFields, QuantityStepper } from './catalogue-ui'
import { describePeriod, hireDays, isIsoDate } from './hire-period'

/** The fields this card shows a message under. */
const CARD_FIELDS = ['from', 'to', 'quantity']

export default function BookingCard({
  model,
  today,
  startIso,
  endIso,
  branchCode,
  quantity,
  branches,
  availability,
  onChangeStart,
  onChangeEnd,
  onChangeBranch,
  onChangeQuantity,
}: {
  model: ModelDetail
  today: string
  startIso: string
  endIso: string
  /** The branch to collect from. Empty until the branch list has arrived. */
  branchCode: string
  quantity: number
  branches: UseQueryResult<BranchList>
  availability: UseQueryResult<ModelAvailability>
  onChangeStart: (value: string) => void
  onChangeEnd: (value: string) => void
  onChangeBranch: (value: string) => void
  onChangeQuantity: (value: number) => void
}) {
  const phase = queryPhase(availability)
  const refused =
    phase === 'failed' &&
    isApiError(availability.error) &&
    availability.error.status === HTTP_UNPROCESSABLE
  const fieldErrors = fieldErrorsFromProblem(availability.error)
  const otherMessages = otherFieldMessages(fieldErrors, CARD_FIELDS)

  const answers = phase === 'ready' ? (availability.data?.branches ?? []) : []
  const here = answers.find((branch) => branch.branchCode === branchCode) ?? null
  const alternative =
    here && !here.available
      ? (answers.find((branch) => branch.available && branch.branchCode !== branchCode) ?? null)
      : null
  const canBook = here !== null && here.available

  // The sum is worked out here so it moves the moment a date or the quantity
  // does. It only appears for a pair of real dates in the right order, and
  // never beside a refusal from the API.
  const datesInOrder = isIsoDate(startIso) && isIsoDate(endIso) && endIso > startIso
  const days = datesInOrder && !refused ? hireDays(startIso, endIso) : null
  const periodLabel = describePeriod(startIso, endIso)

  const basketParams = new URLSearchParams({
    add: model.slug,
    qty: String(quantity),
    from: startIso,
    to: endIso,
    branch: branchCode,
  })

  return (
    <Card title="Book this tool">
      <div className="grid gap-md">
        <PeriodFields
          idPrefix="detail"
          startIso={startIso}
          endIso={endIso}
          minIso={today}
          maxDays={model.maxHireDays}
          onChangeStart={onChangeStart}
          onChangeEnd={onChangeEnd}
          startError={startIso ? fieldErrors.from : 'Choose a collection date.'}
          endError={endIso ? fieldErrors.to : 'Choose a return date.'}
        />
        {branches.isError ? (
          <ErrorState
            what="the branches"
            error={branches.error}
            onRetry={() => void branches.refetch()}
          />
        ) : (
          <BranchSelect
            id="detail-branch"
            branches={branches.data?.items ?? []}
            value={branchCode}
            onChange={(value) => {
              if (value !== ANY_BRANCH) onChangeBranch(value)
            }}
          />
        )}
        <div>
          <QuantityStepper
            id="detail-quantity"
            itemLabel={model.name}
            value={quantity}
            min={MIN_QUANTITY}
            max={MAX_QUANTITY}
            onChange={onChangeQuantity}
          />
          {fieldErrors.quantity && (
            <p className="field-error">
              <span>{fieldErrors.quantity}</span>
            </p>
          )}
        </div>
      </div>

      <div className="mt-md rounded bg-muted p-md">
        {days === null ? (
          <p className="text-sm text-slate-soft">Choose your dates to see the hire charge.</p>
        ) : (
          <>
            <p className="text-sm text-slate-soft">
              {quantity} for {days} {days === 1 ? 'day' : 'days'} at the daily rate
            </p>
            <p className="tabular mt-xs text-xl font-semibold text-ink">
              {money(moneyTimes(model.dailyRate, quantity * days))}
            </p>
            <p className="tabular mt-xs text-sm text-slate-soft">
              Plus {money(moneyTimes(model.depositAmount, quantity))} deposit, refunded on return.
            </p>
          </>
        )}
      </div>

      <div className="mt-md" aria-busy={availability.isFetching}>
        {phase === 'loading' && (
          <p role="status" className="text-sm text-slate-soft">
            Checking the branches for these dates.
          </p>
        )}

        {refused && (
          <Notice tone="error" title="We cannot check those details">
            <p>Check the messages under the fields above and change what they point to.</p>
            {otherMessages.length > 0 && (
              <ul className="mt-xs list-disc pl-lg">
                {otherMessages.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
          </Notice>
        )}

        {phase === 'failed' && !refused && (
          <ErrorState
            what="what is free for these dates"
            error={availability.error}
            onRetry={() => void availability.refetch()}
          />
        )}

        {here && here.available && (
          <p className="flex flex-wrap items-center gap-sm text-sm text-slate-soft" role="status">
            <StatusPill status="AVAILABLE" label={`Free at ${here.branchName}`} />
            {periodLabel && <span>for {periodLabel}</span>}
          </p>
        )}

        {here && !here.available && (
          <Notice tone="warn" title={`Not free at ${here.branchName} for these dates`}>
            <p>
              {alternative
                ? `${alternative.branchName} can supply ${quantity === 1 ? 'it' : `all ${quantity}`} for the same dates.`
                : 'No other branch can supply it for these dates either. Try different dates or a smaller quantity.'}
            </p>
            {alternative && (
              <button
                type="button"
                className="btn-secondary mt-sm px-md"
                onClick={() => onChangeBranch(alternative.branchCode)}
              >
                Collect from {alternative.branchName} instead
              </button>
            )}
          </Notice>
        )}
      </div>

      {canBook ? (
        <Link to={`/basket?${basketParams.toString()}`} className="btn-primary mt-md w-full">
          <ShoppingCart className="h-4 w-4 shrink-0" aria-hidden="true" />
          Add to my hire basket
        </Link>
      ) : (
        <button type="button" className="btn-primary mt-md w-full" disabled>
          <ShoppingCart className="h-4 w-4 shrink-0" aria-hidden="true" />
          Add to my hire basket
        </button>
      )}
    </Card>
  )
}
