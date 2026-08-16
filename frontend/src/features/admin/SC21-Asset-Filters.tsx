/**
 * The four controls that narrow the asset register down to the unit you
 * are actually looking for. Used only by SC-21.
 *
 * A register of four hundred units with no filtering is a list nobody
 * reads, so branch, status and category are all first class here rather
 * than hidden behind a menu.
 */

import { branches, categories } from '../../shared/fixtures'
import { Field } from '../../shared/ui'
import { humanise } from '../../shared/format'
import type { AssetFilterState } from './admin-asset-filters'
import { ANY } from './admin-asset-filters'
import { ALL_STATUSES } from './admin-lifecycle'

export default function AssetFilters({
  value, onChange,
}: {
  value: AssetFilterState
  onChange: (next: AssetFilterState) => void
}) {
  const set = (key: keyof AssetFilterState, next: string) =>
    onChange({ ...value, [key]: next })

  return (
    <div className="mb-md grid gap-md sm:grid-cols-2 lg:grid-cols-4">
      <Field label="Search by tag or tool" htmlFor="asset-search">
        <input
          id="asset-search"
          type="search"
          className="field-input"
          value={value.search}
          placeholder="TSH-DR-0042"
          onChange={(e) => set('search', e.target.value)}
        />
      </Field>
      <Field label="Branch" htmlFor="branch-filter">
        <select
          id="branch-filter" className="field-input" value={value.branch}
          onChange={(e) => set('branch', e.target.value)}
        >
          <option value={ANY}>All branches</option>
          {branches.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
        </select>
      </Field>
      <Field label="Status" htmlFor="status-filter">
        <select
          id="status-filter" className="field-input" value={value.status}
          onChange={(e) => set('status', e.target.value)}
        >
          <option value={ANY}>Every status</option>
          {ALL_STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}
        </select>
      </Field>
      <Field label="Category" htmlFor="asset-category-filter">
        <select
          id="asset-category-filter" className="field-input" value={value.category}
          onChange={(e) => set('category', e.target.value)}
        >
          <option value={ANY}>All categories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </Field>
    </div>
  )
}
