/**
 * SC-01 Catalogue Home.
 *
 * The public shop window and the entry point to everything else. A customer
 * arrives with a job and two dates, so the dates come first and the search
 * they lead to answers against them.
 *
 * The screen reads three lists from the API. The branches fill the branch
 * chooser, the categories fill "Browse by job", and one small page of models
 * fills the shop window. None of those says what is free. Availability is only
 * ever answered for a period, so it lives on SC-02, one press of the search
 * button away, and this screen makes no claim about it.
 *
 * The search form does not wait for any of the three. A customer can pick
 * dates and search while the lists are still loading, or after one has failed.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { MapPin, Search, ShieldCheck, Truck } from 'lucide-react'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import { PageHeader } from '../../shared/ui'
import { todayInBranchTime } from '../../shared/today'
import { ANY_BRANCH, BranchSelect, PeriodFields } from './catalogue-ui'
import { defaultPeriod, describePeriod, hireDays, validatePeriod } from './hire-period'
import { CatalogueStats, CategoryGrid, FeaturedModels } from './SC01-Catalogue-Sections'

/** How many models the shop window puts up front before the customer
 *  starts filtering properly on SC-02. */
const FEATURED_COUNT = 6

const BRANCHES_UNAVAILABLE =
  'We could not load the branch list. You can still search every branch.'

const TRUST_POINTS = [
  { icon: ShieldCheck, text: 'Every unit is checked in and out, so what you book is the unit you get.' },
  { icon: MapPin, text: 'Three branches across Cape Town, with availability shown per branch.' },
  { icon: Truck, text: 'Collect from the branch that has it, not the one that ran out.' },
]

export default function CatalogueHome() {
  const navigate = useNavigate()
  // Read once when the screen opens, so the dates do not shift under a
  // customer who leaves the page open past midnight.
  const [today] = useState(() => todayInBranchTime())
  const [startIso, setStartIso] = useState(() => defaultPeriod(today).startIso)
  const [endIso, setEndIso] = useState(() => defaultPeriod(today).endIso)
  const [branchCode, setBranchCode] = useState<string>(ANY_BRANCH)

  const branches = useQuery(catalogueQueries.branches())
  const categories = useQuery(catalogueQueries.categories())
  const featured = useQuery(catalogueQueries.models({ pageSize: FEATURED_COUNT }))

  const periodError = validatePeriod(startIso, endIso, today)
  const usablePeriod = periodError === null
  const days = usablePeriod ? hireDays(startIso, endIso) : null
  const periodLabel = describePeriod(startIso, endIso)

  function searchNow() {
    if (!usablePeriod) return
    const params = new URLSearchParams({ from: startIso, to: endIso })
    if (branchCode !== ANY_BRANCH) params.set('branch', branchCode)
    navigate(`/search?${params.toString()}`)
  }

  return (
    <>
      <PageHeader
        screenId="SC-01"
        title="Hire tools and plant across Cape Town"
        subtitle="Pick your dates first. The search then shows what is genuinely free for those days at each of our three branches."
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
                minIso={today}
                onChangeStart={setStartIso}
                onChangeEnd={setEndIso}
                startError={periodError ?? undefined}
              />
              <BranchSelect
                id="home-branch"
                branches={branches.data?.items ?? []}
                value={branchCode}
                onChange={setBranchCode}
                allLabel="Any branch"
                error={branches.isError ? BRANCHES_UNAVAILABLE : undefined}
              />
            </div>
            <div className="mt-md flex flex-wrap items-center justify-between gap-md">
              <p className="text-sm text-slate-soft" aria-live="polite">
                {days !== null && periodLabel
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

      <CatalogueStats
        branches={branches}
        categories={categories}
        models={featured}
        days={days}
        periodLabel={periodLabel}
      />
      <CategoryGrid categories={categories} startIso={startIso} endIso={endIso} />
      <FeaturedModels
        models={featured}
        count={FEATURED_COUNT}
        startIso={startIso}
        endIso={endIso}
      />
    </>
  )
}
