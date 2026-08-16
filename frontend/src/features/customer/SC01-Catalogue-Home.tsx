/**
 * SC-01 Catalogue Home.
 *
 * The public shop window and the entry point to everything else. A
 * customer arrives with a job and two dates, so the dates come first and
 * the catalogue answers against them: every count on this screen is for
 * the period in the picker, not a vague "in stock".
 */

import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, MapPin, Search, ShieldCheck, Truck } from 'lucide-react'
import { assets, branches, categories } from '../../shared/fixtures'
import type { BranchCode } from '../../shared/types'
import { formatDate, money } from '../../shared/format'
import { EmptyState, PageHeader, StatTile } from '../../shared/ui'
import { availabilityEverywhere, totalAvailable } from './availability'
import { DEFAULT_END, DEFAULT_START, validatePeriod } from './hire-period'
import { catalogue, categoryIconFor, hireDays, modelsInCategory } from './catalogue-data'
import { BranchSelect, ModelBanner, PeriodFields } from './catalogue-ui'

/** How many models the shop window puts up front before the customer
 *  starts filtering properly on SC-02. */
const FEATURED_COUNT = 6

/** Long enough to read as work being done, short enough not to be a wait. */
const AVAILABILITY_CHECK_MS = 220

const TRUST_POINTS = [
  { icon: ShieldCheck, text: 'Every unit is checked in and out, so what you book is the unit you get.' },
  { icon: MapPin, text: 'Three branches across Cape Town, with stock shown per branch.' },
  { icon: Truck, text: 'Collect from the branch that has it, not the one that ran out.' },
]

export default function CatalogueHome() {
  const navigate = useNavigate()
  const [startIso, setStartIso] = useState(DEFAULT_START)
  const [endIso, setEndIso] = useState(DEFAULT_END)
  const [branchCode, setBranchCode] = useState<BranchCode | 'ALL'>('ALL')
  const [checking, setChecking] = useState(false)

  const periodError = validatePeriod(startIso, endIso)
  const usablePeriod = periodError === null

  // Re-checking the yard whenever the dates move. The prototype has no back
  // end, so this stands in for the request the built system will make.
  useEffect(() => {
    if (!usablePeriod) return
    setChecking(true)
    const timer = window.setTimeout(() => setChecking(false), AVAILABILITY_CHECK_MS)
    return () => window.clearTimeout(timer)
  }, [startIso, endIso, usablePeriod])

  const featured = useMemo(() => {
    if (!usablePeriod) return []
    return catalogue
      .map((model) => ({
        model,
        rows: availabilityEverywhere(model.id, startIso, endIso),
        free: totalAvailable(model.id, startIso, endIso),
      }))
      .sort((a, b) => b.free - a.free || a.model.name.localeCompare(b.model.name))
      .slice(0, FEATURED_COUNT)
  }, [startIso, endIso, usablePeriod])

  const unitsFree = useMemo(
    () =>
      usablePeriod
        ? catalogue.reduce((sum, m) => sum + totalAvailable(m.id, startIso, endIso), 0)
        : 0,
    [startIso, endIso, usablePeriod],
  )

  const days = hireDays(startIso, endIso)
  const periodLabel = `${formatDate(startIso)} to ${formatDate(endIso)}`

  function searchNow() {
    if (!usablePeriod) return
    const params = new URLSearchParams({ from: startIso, to: endIso })
    if (branchCode !== 'ALL') params.set('branch', branchCode)
    navigate(`/search?${params.toString()}`)
  }

  return (
    <>
      <PageHeader
        screenId="SC-01"
        title="Hire tools and plant across Cape Town"
        subtitle="Pick your dates first. Everything below shows what is genuinely free for those days at each of our three branches."
      />

      <section className="card mb-lg overflow-hidden">
        <div className="grid lg:grid-cols-5">
          <div className="bg-gradient-to-br from-ink to-slate p-lg text-white lg:col-span-2 lg:p-xl">
            <p className="font-mono text-xs uppercase tracking-wide text-accent">
              Booked, not promised
            </p>
            <h2 className="mt-sm text-xl font-semibold leading-tight">
              The tool you book is held for you
            </h2>
            <ul className="mt-md flex flex-col gap-md">
              {TRUST_POINTS.map(({ icon: Icon, text }) => (
                <li key={text} className="flex items-start gap-sm text-sm text-white/90">
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden="true" />
                  <span>{text}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* noValidate on purpose. The browser's own bubble for a date
              outside `min` blocks submission and says nothing useful, so the
              form does its own checking and says what to do instead. */}
          <form
            noValidate
            className="p-lg lg:col-span-3 lg:p-xl"
            onSubmit={(e) => {
              e.preventDefault()
              searchNow()
            }}
          >
            <h2 className="text-base font-semibold text-ink">When do you need it?</h2>
            <p className="mt-xs text-sm text-slate-soft">
              We charge by the day and you bring it back the morning it is due.
            </p>
            <div className="mt-md grid gap-md sm:grid-cols-2">
              <PeriodFields
                idPrefix="home"
                startIso={startIso}
                endIso={endIso}
                onChangeStart={setStartIso}
                onChangeEnd={setEndIso}
                error={periodError}
              />
              <BranchSelect
                id="home-branch"
                value={branchCode}
                onChange={setBranchCode}
                allLabel="Any branch"
              />
            </div>
            <div className="mt-md flex flex-wrap items-center justify-between gap-md">
              <p className="text-sm text-slate-soft" aria-live="polite">
                {usablePeriod
                  ? `${days} ${days === 1 ? 'day' : 'days'}, ${periodLabel}.`
                  : 'Fix the dates above and we will check all three branches.'}
              </p>
              <button type="submit" className="btn-primary w-full px-lg sm:w-auto">
                <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
                See what is free
              </button>
            </div>
          </form>
        </div>
      </section>

      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Units free for your dates"
          value={checking ? '...' : unitsFree}
          hint={`Out of ${assets.length} individually tagged units`}
          tone={unitsFree > 0 ? 'good' : 'warn'}
        />
        <StatTile
          label="Models in the catalogue"
          value={catalogue.length}
          hint={`Across ${categories.length} categories`}
        />
        <StatTile label="Branches" value={branches.length} hint="Woodstock, Stikland and Firgrove" />
        <StatTile label="Days in this hire" value={days} hint={periodLabel} />
      </div>

      <section className="mb-lg" aria-labelledby="categories-heading">
        <h2 id="categories-heading" className="mb-md text-lg font-semibold text-ink">
          Browse by job
        </h2>
        <ul className="grid gap-md sm:grid-cols-2 lg:grid-cols-4">
          {categories.map((category) => {
            const Icon = categoryIconFor(category.slug)
            const count = modelsInCategory(category.id).length
            return (
              <li key={category.id}>
                <Link
                  to={`/search?category=${category.slug}&from=${startIso}&to=${endIso}`}
                  className="card flex h-full cursor-pointer items-start gap-md p-md transition-shadow duration-200 hover:shadow-raised"
                >
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded bg-accent-wash">
                    <Icon className="h-5 w-5 text-ink" aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-base font-semibold text-ink">{category.name}</span>
                    <span className="tabular mt-xs block text-sm text-slate-soft">
                      {count} {count === 1 ? 'model' : 'models'}
                    </span>
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      </section>

      <section aria-labelledby="featured-heading">
        <div className="mb-md flex flex-wrap items-end justify-between gap-sm">
          <h2 id="featured-heading" className="text-lg font-semibold text-ink">
            Free for {periodLabel}
          </h2>
          <Link to={`/search?from=${startIso}&to=${endIso}`} className="btn-secondary px-md">
            See the full catalogue
            <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
          </Link>
        </div>

        {featured.length === 0 ? (
          <div className="card">
            <EmptyState
              title="Nothing to show for these dates yet"
              body="Choose a collection date of today or later and a return date after it, and the catalogue will fill in."
            />
          </div>
        ) : (
          <ul className="grid gap-md sm:grid-cols-2 lg:grid-cols-3" aria-busy={checking}>
            {featured.map(({ model, rows, free }) => {
              const branchesWithStock = rows.filter((r) => r.availableUnits > 0)
              return (
                <li key={model.id}>
                  <Link
                    to={`/model/${model.id}?from=${startIso}&to=${endIso}`}
                    className="card flex h-full cursor-pointer flex-col transition-shadow duration-200 hover:shadow-raised"
                  >
                    <ModelBanner model={model} />
                    <div className="flex flex-1 flex-col p-md">
                      <p className="tabular text-lg font-semibold text-ink">
                        {money(model.dailyRate)}
                        <span className="text-sm font-normal text-slate-soft"> per day</span>
                      </p>
                      <p className="mt-xs text-sm text-slate-soft">
                        Deposit {money(model.depositAmount)}
                      </p>
                      <p className="mt-sm flex-1 text-sm text-slate-soft">
                        {free > 0
                          ? `${free} free at ${branchesWithStock.length} of ${rows.length} branches for these dates.`
                          : 'None free for these dates. Open it to see the next free day.'}
                      </p>
                      <span className="mt-md inline-flex items-center gap-xs text-sm font-semibold text-ink">
                        See dates and book
                        <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                      </span>
                    </div>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </>
  )
}
