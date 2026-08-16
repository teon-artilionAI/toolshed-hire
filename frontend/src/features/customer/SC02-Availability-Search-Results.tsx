/**
 * SC-02 Availability Search Results.
 *
 * This is where the double booking problem is visibly solved. Every row
 * answers one question honestly: can I have this one, at this branch,
 * for these exact days. When the answer is no, the row says why and names
 * the nearest branch that can supply it instead of leaving the customer
 * to guess.
 *
 * Filters live in the address bar as well as in state, so a counter
 * assistant can send a customer a link to the search they just ran.
 */

import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search, SlidersHorizontal } from 'lucide-react'
import { branches, categories } from '../../shared/fixtures'
import type { BranchCode } from '../../shared/types'
import { formatDate } from '../../shared/format'
import { EmptyState, Field, Notice, PageHeader } from '../../shared/ui'
import { availabilityEverywhere, nearestBranchWithStock } from './availability'
import { DEFAULT_END, DEFAULT_START, validatePeriod } from './hire-period'
import { catalogue, categoryOf, hireDays } from './catalogue-data'
import { BranchSelect, PeriodFields } from './catalogue-ui'
import { readBranchFilter } from './branch-params'
import SearchResultRow from './search-result-row'

export default function SearchResults() {
  const [params, setParams] = useSearchParams()

  const [query, setQuery] = useState(params.get('q') ?? '')
  const [categorySlug, setCategorySlug] = useState(params.get('category') ?? 'ALL')
  const [branchCode, setBranchCode] = useState<BranchCode | 'ALL'>(
    readBranchFilter(params.get('branch')),
  )
  const [startIso, setStartIso] = useState(params.get('from') ?? DEFAULT_START)
  const [endIso, setEndIso] = useState(params.get('to') ?? DEFAULT_END)
  // Off by default. A catalogue that quietly hides everything already
  // booked teaches a customer nothing about when it comes back.
  const [freeOnly, setFreeOnly] = useState(false)

  const periodError = validatePeriod(startIso, endIso)
  const usablePeriod = periodError === null

  // Keep the address bar in step so the search can be shared or bookmarked.
  useEffect(() => {
    const next = new URLSearchParams({ from: startIso, to: endIso })
    if (query.trim()) next.set('q', query.trim())
    if (categorySlug !== 'ALL') next.set('category', categorySlug)
    if (branchCode !== 'ALL') next.set('branch', branchCode)
    setParams(next, { replace: true })
  }, [query, categorySlug, branchCode, startIso, endIso, setParams])

  const results = useMemo(() => {
    if (!usablePeriod) return []
    const needle = query.trim().toLowerCase()
    return catalogue
      .filter((model) => {
        const category = categoryOf(model)
        if (categorySlug !== 'ALL' && category?.slug !== categorySlug) return false
        if (!needle) return true
        return `${model.name} ${model.manufacturer} ${model.sku} ${category?.name ?? ''}`
          .toLowerCase()
          .includes(needle)
      })
      .map((model) => {
        const rows = availabilityEverywhere(model.id, startIso, endIso)
        const here =
          branchCode === 'ALL'
            ? null
            : (rows.find((r) => r.branch.code === branchCode) ?? null)
        const free = here ? here.availableUnits : rows.reduce((n, r) => n + r.availableUnits, 0)
        return { model, rows, here, free }
      })
      .filter((row) => (freeOnly ? row.free > 0 : true))
      .sort((a, b) => b.free - a.free || a.model.name.localeCompare(b.model.name))
  }, [query, categorySlug, branchCode, startIso, endIso, freeOnly, usablePeriod])

  const days = hireDays(startIso, endIso)
  const periodLabel = `${formatDate(startIso)} to ${formatDate(endIso)}`
  const scopeLabel =
    branchCode === 'ALL'
      ? 'across all three branches'
      : `at ${branches.find((b) => b.code === branchCode)?.name ?? 'the chosen branch'}`

  return (
    <>
      <PageHeader
        screenId="SC-02"
        title="What is free for your dates"
        subtitle={`Counts are for the whole hire, ${periodLabel}. A unit only counts as free if it is free every day of the period.`}
      />

      <form
        className="card mb-lg p-lg"
        aria-label="Filter the catalogue"
        onSubmit={(e) => e.preventDefault()}
      >
        <h2 className="mb-md flex items-center gap-sm text-sm font-semibold uppercase tracking-wide text-slate-soft">
          <SlidersHorizontal className="h-4 w-4 shrink-0" aria-hidden="true" />
          Narrow it down
        </h2>
        <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Search by tool or make" htmlFor="search-q">
            <input
              id="search-q"
              type="search"
              className="field-input"
              placeholder="Breaker, Bosch, mixer"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </Field>
          <Field label="Category" htmlFor="search-category">
            <select
              id="search-category"
              className="field-input cursor-pointer"
              value={categorySlug}
              onChange={(e) => setCategorySlug(e.target.value)}
            >
              <option value="ALL">Every category</option>
              {categories.map((c) => (
                <option key={c.id} value={c.slug}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          <BranchSelect
            id="search-branch"
            label="Branch"
            value={branchCode}
            onChange={setBranchCode}
            allLabel="Any branch"
          />
          <PeriodFields
            idPrefix="search"
            startIso={startIso}
            endIso={endIso}
            onChangeStart={setStartIso}
            onChangeEnd={setEndIso}
            error={periodError}
          />
          <div className="flex items-end">
            <label className="flex min-h-[2.75rem] cursor-pointer items-center gap-sm text-sm text-ink">
              <input
                type="checkbox"
                className="h-6 w-6 cursor-pointer accent-accent"
                checked={freeOnly}
                onChange={(e) => setFreeOnly(e.target.checked)}
              />
              Hide anything that is not free
            </label>
          </div>
        </div>
      </form>

      {!usablePeriod && (
        <div className="mb-lg">
          <Notice tone="error" title="We cannot search these dates">
            {periodError}
          </Notice>
        </div>
      )}

      <p className="mb-md text-sm text-slate-soft" role="status">
        {usablePeriod
          ? `${results.length} of ${catalogue.length} models match, ${scopeLabel}, for ${days} ${days === 1 ? 'day' : 'days'}.`
          : 'Waiting on a usable pair of dates.'}
      </p>

      {results.length === 0 ? (
        <div className="card">
          <EmptyState
            title="Nothing matches that search"
            body="Try a wider category, a different pair of dates, or untick the free only filter to see what is out and when it comes back."
            action={
              <button
                type="button"
                className="btn-secondary px-md"
                onClick={() => {
                  setQuery('')
                  setCategorySlug('ALL')
                  setBranchCode('ALL')
                  setFreeOnly(false)
                }}
              >
                <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
                Clear the filters
              </button>
            }
          />
        </div>
      ) : (
        <ul className="flex flex-col gap-md">
          {results.map(({ model, rows, here }) => (
            <SearchResultRow
              key={model.id}
              rows={rows}
              here={here}
              name={model.name}
              manufacturer={model.manufacturer}
              tone={model.imageTone}
              categoryName={categoryOf(model)?.name ?? 'Uncategorised'}
              dailyRate={model.dailyRate}
              deposit={model.depositAmount}
              detailHref={`/model/${model.id}?from=${startIso}&to=${endIso}${
                branchCode === 'ALL' ? '' : `&branch=${branchCode}`
              }`}
              alternative={
                here && here.availableUnits === 0
                  ? nearestBranchWithStock(model.id, here.branch.code, startIso, endIso)
                  : null
              }
              onSwitchBranch={setBranchCode}
            />
          ))}
        </ul>
      )}
    </>
  )
}
