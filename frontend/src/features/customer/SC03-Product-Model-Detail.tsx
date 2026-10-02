/**
 * SC-03 Product Model Detail.
 *
 * One catalogue entry, read from the API by the slug in the address. The
 * description, the daily and weekly rates, the deposit and the late fee are
 * all on the same screen, because a customer who finds out about the late fee
 * at the counter feels caught out.
 *
 * Beside it, the booking card asks the API whether each branch can supply the
 * quantity wanted for the dates chosen. The answer per branch is free or not
 * free. The API sends no unit counts, so the screen shows none.
 *
 * The card also shows what the hire will cost. That figure is the server's
 * quote for the same dates and quantity. This screen does no sum of its own.
 */

import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { MIN_QUANTITY } from '../../shared/api/catalogue'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { isApiError } from '../../shared/api-problem'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { money } from '../../shared/format'
import { Card, Notice, PageHeader } from '../../shared/ui'
import { todayInBranchTime } from '../../shared/today'
import { searchHref } from './catalogue-links'
import { AvailabilityChip } from './catalogue-ui'
import { defaultPeriod, describePeriod } from './hire-period'
import { ModelBanner } from './model-picture'
import BookingCard from './SC03-Booking-Card'

const HTTP_NOT_FOUND = 404

export default function ModelDetail() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const [today] = useState(() => todayInBranchTime())

  const [startIso, setStartIso] = useState(() => params.get('from') ?? defaultPeriod(today).startIso)
  const [endIso, setEndIso] = useState(() => params.get('to') ?? defaultPeriod(today).endIso)
  const [chosenBranch, setChosenBranch] = useState(() => params.get('branch') ?? '')
  const [quantity, setQuantity] = useState(MIN_QUANTITY)

  const model = useQuery({ ...catalogueQueries.model(slug), enabled: slug !== '' })
  const branches = useQuery(catalogueQueries.branches())
  const availability = useQuery({
    ...catalogueQueries.modelAvailability(slug, { from: startIso, to: endIso, quantity }),
    enabled: slug !== '' && startIso !== '' && endIso !== '',
  })
  const quote = useQuery({
    ...catalogueQueries.modelQuote(slug, { from: startIso, to: endIso, quantity }),
    enabled: slug !== '' && startIso !== '' && endIso !== '',
  })

  // The branch in the address is user input. Once the list is here, a code it
  // does not hold gives way to the first branch, so the card always asks about
  // a branch that exists.
  const branchItems = branches.data?.items ?? []
  const branchCode =
    branchItems.length === 0 || branchItems.some((branch) => branch.code === chosenBranch)
      ? chosenBranch
      : branchItems[0].code

  const modelPhase = queryPhase(model)
  const notFound = isApiError(model.error) && model.error.status === HTTP_NOT_FOUND
  const backToResults = searchHref({ from: startIso, to: endIso })

  if (modelPhase === 'failed' && notFound) {
    return (
      <>
        <PageHeader
          screenId="SC-03"
          title="We cannot find that tool"
          subtitle="It may have been withdrawn from hire, or the address may have been mistyped."
        />
        <Notice tone="error" title="This catalogue entry is not available">
          <p>
            Nothing is hired under the reference <span className="font-mono">{slug}</span>. Go
            back to the search and pick from what we currently hire.
          </p>
          <Link to="/search" className="btn-primary mt-md px-lg">
            <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
            Back to the search
          </Link>
        </Notice>
      </>
    )
  }

  if (modelPhase === 'failed') {
    return (
      <>
        <PageHeader screenId="SC-03" title="Tool details" />
        <ErrorState what="this tool" error={model.error} onRetry={() => void model.refetch()}>
          <Link to={backToResults} className="btn-ghost px-md">
            Back to results
          </Link>
        </ErrorState>
      </>
    )
  }

  if (!model.data) {
    return <LoadingState label="Loading this tool" shape="detail" count={2} />
  }

  const tool = model.data
  const availabilityPhase = queryPhase(availability)
  const answers = availabilityPhase === 'ready' ? (availability.data?.branches ?? []) : []
  const periodLabel = describePeriod(startIso, endIso)

  return (
    <>
      <PageHeader
        screenId="SC-03"
        title={tool.name}
        subtitle={`${tool.manufacturer}. ${tool.categoryName}.`}
        actions={
          <Link to={backToResults} className="btn-secondary px-md">
            <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
            Back to results
          </Link>
        }
      />

      <div className="mb-lg grid gap-lg lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <div className="card overflow-hidden">
            <ModelBanner
              name={tool.name}
              manufacturer={tool.manufacturer}
              categoryCode={tool.categoryCode}
              imagePath={tool.imagePath}
              height="h-32 sm:h-44"
            />
            <div className="p-lg">
              <p className="text-base text-ink">{tool.shortDescription}</p>
              {tool.longDescription && (
                <p className="mt-sm text-sm text-slate-soft">{tool.longDescription}</p>
              )}
              <dl className="mt-lg grid gap-md sm:grid-cols-2">
                <Spec term="Hire rate" detail={`${money(tool.dailyRate)} per day`} />
                <Spec term="Weekly rate" detail={`${money(tool.weeklyRate)} per week`} />
                <Spec term="Refundable deposit" detail={money(tool.depositAmount)} />
                <Spec
                  term="Late fee"
                  detail={`${money(tool.lateFeePerDay)} per day past the return date`}
                />
                <Spec
                  term="Hire length"
                  detail={`${tool.minHireDays} to ${tool.maxHireDays} days`}
                />
                <Spec term="Model number" detail={tool.modelNumber} mono />
                <Spec term="Catalogue number" detail={tool.sku} mono />
              </dl>
            </div>
          </div>
        </div>

        <div className="min-w-0">
          <BookingCard
            model={tool}
            today={today}
            startIso={startIso}
            endIso={endIso}
            branchCode={branchCode}
            quantity={quantity}
            branches={branches}
            availability={availability}
            quote={quote}
            onChangeStart={setStartIso}
            onChangeEnd={setEndIso}
            onChangeBranch={setChosenBranch}
            onChangeQuantity={setQuantity}
          />
        </div>
      </div>

      <Card title="At each branch for these dates">
        {availabilityPhase === 'loading' && (
          <p className="text-sm text-slate-soft">Checking every branch.</p>
        )}
        {(availabilityPhase === 'failed' || availabilityPhase === 'idle') && (
          <p className="text-sm text-slate-soft">
            Each branch is shown here once the dates above can be checked.
          </p>
        )}
        {availabilityPhase === 'ready' && (
          <>
            <ul className="flex flex-wrap gap-sm" aria-busy={availability.isFetching}>
              {answers.map((branch) => (
                <li key={branch.branchCode}>
                  <AvailabilityChip branchName={branch.branchName} available={branch.available} />
                </li>
              ))}
            </ul>
            <p className="mt-md text-sm text-slate-soft">
              For {quantity} {quantity === 1 ? 'unit' : 'units'}
              {periodLabel ? `, ${periodLabel}` : ''}. A branch only counts as free if it can
              supply that many for every day of the hire.
            </p>
          </>
        )}
      </Card>
    </>
  )
}

function Spec({
  term,
  detail,
  mono = false,
}: {
  term: string
  detail: string
  mono?: boolean
}) {
  return (
    <div className="border-t border-line pt-sm">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-soft">{term}</dt>
      <dd className={`mt-xs text-base text-ink ${mono ? 'font-mono' : 'tabular'}`}>{detail}</dd>
    </div>
  )
}
