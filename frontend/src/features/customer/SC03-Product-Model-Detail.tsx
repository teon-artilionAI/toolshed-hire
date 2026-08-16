/**
 * SC-03 Product Model Detail.
 *
 * One catalogue entry, with the fourteen day availability strip that
 * answers the question a counter gets asked twenty times a day: not "have
 * you got one" but "when can I have one". Specification, daily rate,
 * deposit and the late fee are all on the same screen, because a customer
 * who finds out about the late fee at the counter feels caught out.
 */

import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Clock, ShoppingCart } from 'lucide-react'
import type { BranchCode } from '../../shared/types'
import { formatDate, money } from '../../shared/format'
import { Card, Notice, PageHeader, StatusPill } from '../../shared/ui'
import {
  availabilityAt,
  availabilityEverywhere,
  fleetAt,
  nearestBranchWithStock,
} from './availability'
import { DEFAULT_END, DEFAULT_START, validatePeriod } from './hire-period'
import AvailabilityStrip from './availability-strip'
import { readBranch } from './branch-params'
import { categoryOf, hireDays, modelById } from './catalogue-data'
import {
  AvailabilityChip,
  BranchSelect,
  ModelBanner,
  PeriodFields,
  QuantityStepper,
} from './catalogue-ui'

export default function ModelDetail() {
  const { modelId = '' } = useParams()
  const [params] = useSearchParams()
  const model = modelById(modelId)

  const [startIso, setStartIso] = useState(params.get('from') ?? DEFAULT_START)
  const [endIso, setEndIso] = useState(params.get('to') ?? DEFAULT_END)
  const [branchCode, setBranchCode] = useState<BranchCode>(readBranch(params.get('branch')))
  const [quantity, setQuantity] = useState(1)

  const periodError = validatePeriod(startIso, endIso)
  const usablePeriod = periodError === null

  const here = useMemo(
    () => (model && usablePeriod ? availabilityAt(model.id, branchCode, startIso, endIso) : null),
    [model, branchCode, startIso, endIso, usablePeriod],
  )
  const everywhere = useMemo(
    () => (model && usablePeriod ? availabilityEverywhere(model.id, startIso, endIso) : []),
    [model, startIso, endIso, usablePeriod],
  )

  if (!model || !model.published) {
    return (
      <>
        <PageHeader
          screenId="SC-03"
          title="We cannot find that tool"
          subtitle="It may have been withdrawn from hire, or the address may have been mistyped."
        />
        <Notice tone="error" title="This catalogue entry is not available">
          <p>
            Nothing is hired under the reference <span className="font-mono">{modelId}</span>. Go
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

  const days = hireDays(startIso, endIso)
  const fleet = fleetAt(model.id, branchCode)
  const shortfall = here !== null && quantity > here.availableUnits
  const alternative =
    shortfall && here
      ? nearestBranchWithStock(model.id, here.branch.code, startIso, endIso, quantity)
      : null
  const canBook = usablePeriod && !shortfall && quantity > 0

  const basketHref = `/basket?add=${model.id}&qty=${quantity}&from=${startIso}&to=${endIso}&branch=${branchCode}`
  const stripStart = startIso < DEFAULT_START ? DEFAULT_START : startIso

  return (
    <>
      <PageHeader
        screenId="SC-03"
        title={model.name}
        subtitle={`${model.manufacturer}. ${categoryOf(model)?.name ?? 'Uncategorised'}.`}
        actions={
          <Link to={`/search?from=${startIso}&to=${endIso}`} className="btn-secondary px-md">
            <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
            Back to results
          </Link>
        }
      />

      <div className="mb-lg grid gap-lg lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <div className="card overflow-hidden">
            <ModelBanner model={model} height="h-40 sm:h-56" />
            <div className="p-lg">
              <p className="text-base text-ink">{model.description}</p>
              <dl className="mt-lg grid gap-md sm:grid-cols-2">
                <Spec term="Hire rate" detail={`${money(model.dailyRate)} per day`} />
                <Spec term="Refundable deposit" detail={money(model.depositAmount)} />
                <Spec
                  term="Late fee"
                  detail={`${money(model.lateFeePerDay)} per day past the return date`}
                />
                <Spec term="Replacement value" detail={money(model.replacementValue)} />
                <Spec term="Catalogue number" detail={model.sku} mono />
                <Spec
                  term="Units in the fleet"
                  detail={`${fleet.length} at ${here?.branch.name ?? 'this branch'}`}
                />
              </dl>
            </div>
          </div>
        </div>

        <div className="min-w-0">
          <Card title="Book this tool">
            <div className="grid gap-md">
              <PeriodFields
                idPrefix="detail"
                startIso={startIso}
                endIso={endIso}
                onChangeStart={setStartIso}
                onChangeEnd={setEndIso}
                error={periodError}
              />
              <BranchSelect
                id="detail-branch"
                value={branchCode}
                onChange={(value) => setBranchCode(value as BranchCode)}
              />
              {/* The cap is the branch's whole fleet, not what is free, so a
                  customer who asks for more than is available is told why
                  rather than silently stopped by a dead button. */}
              <QuantityStepper
                id="detail-quantity"
                itemLabel={model.name}
                value={quantity}
                max={Math.max(1, fleet.length)}
                onChange={setQuantity}
              />
            </div>

            <div className="mt-md rounded bg-muted p-md">
              <p className="text-sm text-slate-soft">
                {quantity} for {days} {days === 1 ? 'day' : 'days'}
              </p>
              <p className="tabular mt-xs text-xl font-semibold text-ink">
                {money(quantity * days * model.dailyRate)}
              </p>
              <p className="tabular mt-xs text-sm text-slate-soft">
                Plus {money(quantity * model.depositAmount)} deposit, refunded on return.
              </p>
            </div>

            {here && !shortfall && (
              <p className="mt-md flex items-center gap-sm text-sm text-slate-soft">
                <StatusPill status="AVAILABLE" label={`${here.availableUnits} free here`} />
                for {formatDate(startIso)} to {formatDate(endIso)}
              </p>
            )}

            {shortfall && here && (
              <div className="mt-md">
                <Notice
                  tone="warn"
                  title={
                    here.availableUnits === 0
                      ? `None free at ${here.branch.name} for these dates`
                      : `Only ${here.availableUnits} free at ${here.branch.name}`
                  }
                >
                  <p>{here.reason ?? 'The units here are committed for the period you chose.'}</p>
                  <p className="mt-xs">
                    {alternative
                      ? `${alternative.branch.name} has ${alternative.availableUnits} free for the same dates.`
                      : 'Try shorter dates, or check the strip below for the first day it frees up.'}
                  </p>
                  {alternative && (
                    <button
                      type="button"
                      className="btn-secondary mt-sm px-md"
                      onClick={() => setBranchCode(alternative.branch.code)}
                    >
                      Collect from {alternative.branch.name} instead
                    </button>
                  )}
                </Notice>
              </div>
            )}

            {canBook ? (
              <Link to={basketHref} className="btn-primary mt-md w-full">
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
        </div>
      </div>

      <section className="mb-lg" aria-labelledby="strip-heading">
        <div className="mb-md">
          <h2 id="strip-heading" className="text-lg font-semibold text-ink">
            The next fourteen days
          </h2>
          <p className="mt-xs flex items-start gap-sm text-sm text-slate-soft">
            <Clock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              Units free each day at each branch, from {formatDate(stripStart)}. Scroll the
              table sideways for the full fortnight. The counts change as you change your
              dates.
            </span>
          </p>
        </div>
        <AvailabilityStrip
          modelId={model.id}
          fromIso={stripStart}
          startIso={startIso}
          endIso={endIso}
        />
      </section>

      <Card title="Where it is kept right now">
        <ul className="flex flex-wrap gap-sm">
          {everywhere.map((row) => (
            <li key={row.branch.code}>
              <AvailabilityChip row={row} wanted={quantity} />
            </li>
          ))}
        </ul>
        <ul className="mt-md flex flex-col gap-sm text-sm text-slate-soft">
          {everywhere
            .filter((row) => row.reason !== null)
            .map((row) => (
              <li key={row.branch.code}>
                <span className="font-medium text-ink">{row.branch.name}:</span> {row.reason}.
              </li>
            ))}
        </ul>
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
