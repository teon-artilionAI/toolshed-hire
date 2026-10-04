/**
 * The controls above the SC-22 report.
 *
 * The period, the grouping, and the branch and category filters. Each change
 * goes straight into the address and the report is asked for again, so there
 * is no button to press. A date is only taken once it is a whole day, so a
 * date half typed never asks the server anything. When the server refuses a
 * value, its message is under the control it is about.
 *
 * The branches and the categories come from the catalogue routes. Each list
 * has its own loading and failed state. While a list is missing, its filter
 * still offers every branch or every category, which is the report as it
 * stands, and a failed list offers to be read again.
 */

import { useState } from 'react'
import type { ChangeEvent } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { RotateCw, SlidersHorizontal } from 'lucide-react'
import type { BranchList, Category, CategoryList, IsoDate, ReportGrouping } from '../../shared/api/contract'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { REPORT_GROUPINGS } from '../../shared/api/reporting'
import { Field } from '../../shared/ui'
import { ANY_BRANCH, BranchSelect } from '../customer/catalogue-ui'
import type { ReportFilters as Filters } from './report-address'
import { GROUPING_LABEL } from './report-labels'

const EVERY_CATEGORY = ''
const DATE_SHAPE = /^\d{4}-\d{2}-\d{2}$/
const SELECT_CLASS = 'field-input cursor-pointer'

/** Said under a filter while its list is on its way. */
const LOADING_HELP = {
  branches: 'Loading the branches.',
  categories: 'Loading the categories.',
} as const

/** A category with the name of its parent, so two of the same name read apart. */
function categoryLabel(category: Category, all: readonly Category[]): string {
  const parent = all.find((candidate) => candidate.code === category.parentCode)
  return parent ? `${category.name}, in ${parent.name}` : category.name
}

function describedBy(...ids: (string | false)[]): string | undefined {
  const joined = ids.filter((id): id is string => id !== false).join(' ')
  return joined === '' ? undefined : joined
}

/** A line under a filter whose list could not be loaded, with the way to try again. */
function ListFailed({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <div className="mt-xs flex flex-wrap items-center gap-sm text-sm text-slate-soft">
      <span>We could not load the {what}, so only every one can be chosen.</span>
      <button type="button" className="btn-ghost px-sm" onClick={onRetry}>
        <RotateCw className="h-4 w-4 shrink-0" aria-hidden="true" />
        Load the {what} again
      </button>
    </div>
  )
}

/**
 * One day of the period. It keeps what is being typed and passes on only a
 * whole day, and it follows the address when the address changes.
 */
function DayField({
  id,
  label,
  help,
  value,
  error,
  onDay,
}: {
  id: string
  label: string
  help?: string
  value: IsoDate
  error?: string
  onDay: (day: IsoDate) => void
}) {
  const [draft, setDraft] = useState(value)
  const [lastValue, setLastValue] = useState(value)
  if (value !== lastValue) {
    setLastValue(value)
    setDraft(value)
  }
  function change(event: ChangeEvent<HTMLInputElement>) {
    setDraft(event.target.value)
    if (DATE_SHAPE.test(event.target.value) && event.target.value !== value) onDay(event.target.value)
  }
  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <input
        id={id}
        type="date"
        className={SELECT_CLASS}
        value={draft}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(help !== undefined && `${id}-help`, error !== undefined && `${id}-error`)}
        onChange={change}
      />
    </Field>
  )
}

export default function ReportFilters({
  filters,
  fieldErrors,
  branches,
  categories,
  onChange,
}: {
  filters: Filters
  fieldErrors: FieldErrors
  branches: UseQueryResult<BranchList>
  categories: UseQueryResult<CategoryList>
  onChange: (changes: Partial<Filters>) => void
}) {
  const categoryItems = categories.data?.items ?? []
  const chosenCategory = filters.categorySlug ?? EVERY_CATEGORY
  const knownCategory =
    chosenCategory === EVERY_CATEGORY || categoryItems.some((category) => category.slug === chosenCategory)
  const categoryHelp = queryPhase(categories) === 'loading' ? LOADING_HELP.categories : undefined

  return (
    <form className="card mb-lg p-lg" aria-label="Choose what the report shows" onSubmit={(e) => e.preventDefault()}>
      <h2 className="mb-md flex items-center gap-sm text-sm font-semibold uppercase tracking-wide text-slate-soft">
        <SlidersHorizontal className="h-4 w-4 shrink-0" aria-hidden="true" />
        Period and breakdown
      </h2>
      <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-3">
        <DayField
          id="report-from"
          label="From"
          value={filters.from}
          error={fieldErrors.from}
          onDay={(from) => onChange({ from })}
        />
        <DayField
          id="report-to"
          label="To, not included"
          help="Days are counted from the first date up to but not including this one, so 1 September to 1 October is the whole of September."
          value={filters.to}
          error={fieldErrors.to}
          onDay={(to) => onChange({ to })}
        />
        <Field label="Break the figures down by" htmlFor="report-group" error={fieldErrors.groupBy}>
          <select
            id="report-group"
            className={SELECT_CLASS}
            value={filters.groupBy}
            aria-invalid={fieldErrors.groupBy ? true : undefined}
            aria-describedby={fieldErrors.groupBy ? 'report-group-error' : undefined}
            onChange={(e) => {
              const groupBy = REPORT_GROUPINGS.find((grouping: ReportGrouping) => grouping === e.target.value)
              if (groupBy) onChange({ groupBy })
            }}
          >
            {REPORT_GROUPINGS.map((grouping) => (
              <option key={grouping} value={grouping}>
                {GROUPING_LABEL[grouping]}
              </option>
            ))}
          </select>
        </Field>
        <div>
          <BranchSelect
            id="report-branch"
            label="Branch"
            branches={branches.data?.items ?? []}
            value={filters.branchCode ?? ANY_BRANCH}
            onChange={(code) => onChange({ branchCode: code === ANY_BRANCH ? null : code })}
            allLabel="Every branch"
            help={queryPhase(branches) === 'loading' ? LOADING_HELP.branches : undefined}
            error={fieldErrors.branchCode}
          />
          {queryPhase(branches) === 'failed' && (
            <ListFailed what="branches" onRetry={() => void branches.refetch()} />
          )}
        </div>
        <div>
          <Field label="Category" htmlFor="report-category" help={categoryHelp} error={fieldErrors.categorySlug}>
            <select
              id="report-category"
              className={SELECT_CLASS}
              value={chosenCategory}
              aria-invalid={fieldErrors.categorySlug ? true : undefined}
              aria-describedby={describedBy(
                categoryHelp !== undefined && 'report-category-help',
                fieldErrors.categorySlug !== undefined && 'report-category-error',
              )}
              onChange={(e) => onChange({ categorySlug: e.target.value === EVERY_CATEGORY ? null : e.target.value })}
            >
              <option value={EVERY_CATEGORY}>Every category</option>
              {!knownCategory && <option value={chosenCategory}>Chosen category</option>}
              {categoryItems.map((category) => (
                <option key={category.code} value={category.slug}>
                  {categoryLabel(category, categoryItems)}
                </option>
              ))}
            </select>
          </Field>
          {queryPhase(categories) === 'failed' && (
            <ListFailed what="categories" onRetry={() => void categories.refetch()} />
          )}
        </div>
      </div>
    </form>
  )
}
