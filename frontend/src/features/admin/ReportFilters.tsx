/**
 * The controls above the SC-22 report.
 *
 * Kept out of the screen file because five selects with labels is a lot of
 * markup for very little thinking, and the report itself is the interesting
 * part. Every control is a real form control with a real label, so it works
 * on a keyboard and reads correctly to a screen reader.
 */

import type { BranchCode } from '../../shared/types'
import { branches, categories } from '../../shared/fixtures'
import { Field } from '../../shared/ui'
import { REPORT_PERIODS } from './report-metrics'
import { GROUP_OPTIONS, SORT_OPTIONS } from './report-grouping'
import type { GroupBy, SortKey } from './report-grouping'

const SELECT_CLASS = 'field-input cursor-pointer transition-colors duration-200'

export interface ReportFilterState {
  periodId: string
  groupBy: GroupBy
  branchCode: BranchCode | 'ALL'
  categoryId: string | 'ALL'
  sortKey: SortKey
}

export default function ReportFilters({
  value,
  onChange,
}: {
  value: ReportFilterState
  onChange: (next: ReportFilterState) => void
}) {
  const set = <K extends keyof ReportFilterState>(
    key: K,
    next: ReportFilterState[K],
  ) => onChange({ ...value, [key]: next })

  return (
    <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-3">
      <Field label="Period" htmlFor="report-period">
        <select
          id="report-period"
          className={SELECT_CLASS}
          value={value.periodId}
          onChange={(e) => set('periodId', e.target.value)}
        >
          {REPORT_PERIODS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Break the figures down by" htmlFor="report-group">
        <select
          id="report-group"
          className={SELECT_CLASS}
          value={value.groupBy}
          onChange={(e) => set('groupBy', e.target.value as GroupBy)}
        >
          {GROUP_OPTIONS.map((g) => (
            <option key={g.id} value={g.id}>
              {g.label}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Branch" htmlFor="report-branch">
        <select
          id="report-branch"
          className={SELECT_CLASS}
          value={value.branchCode}
          onChange={(e) =>
            set('branchCode', e.target.value as BranchCode | 'ALL')
          }
        >
          <option value="ALL">All three branches</option>
          {branches.map((b) => (
            <option key={b.code} value={b.code}>
              {b.name}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Category" htmlFor="report-category">
        <select
          id="report-category"
          className={SELECT_CLASS}
          value={value.categoryId}
          onChange={(e) => set('categoryId', e.target.value)}
        >
          <option value="ALL">Every category</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Order by" htmlFor="report-sort">
        <select
          id="report-sort"
          className={SELECT_CLASS}
          value={value.sortKey}
          onChange={(e) => set('sortKey', e.target.value as SortKey)}
        >
          {SORT_OPTIONS.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </Field>
    </div>
  )
}
