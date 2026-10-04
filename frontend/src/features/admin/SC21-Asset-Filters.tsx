/**
 * The search and the three filters above the register on SC-21.
 *
 * The search, the branch, the status and the model live in the address under
 * the names the API takes. The search asks a moment after the last key, so it
 * never asks on every keystroke, and the menus apply as they are chosen. The
 * branches are the API's own list, the statuses are every status a unit can
 * be in, in words, and the model is found by searching for it, because the
 * catalogue holds too many for one menu.
 *
 * A refusal of a filter is put under the control it names.
 */

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { ASSET_STATUSES } from '../../shared/api/locator'
import { queryPhase } from '../../shared/api/query-phase'
import { SelectInput, TextInput } from '../counter/counter-fields'
import { ASSET_STATUS_LABEL } from '../counter/counter-labels'
import type { AssetFilters as Filters } from './asset-address'
import { FIRST_PAGE } from './report-address'
import { ModelPicker } from './SC21-Model-Picker'

/** How long the search waits after the last key before it asks. */
const SEARCH_DEBOUNCE_MS = 300

const EVERY = ''

const STATUS_OPTIONS = [
  { value: EVERY, label: 'Every status' },
  ...ASSET_STATUSES.map((status) => ({ value: status, label: ASSET_STATUS_LABEL[status] })),
]

function useBranchOptions(chosen: string | null) {
  const branches = useQuery(catalogueQueries.branches())
  const listed = (branches.data?.items ?? []).map((branch) => ({ value: branch.code, label: branch.name }))
  const unknown =
    chosen !== null && !listed.some((option) => option.value === chosen) ? [{ value: chosen, label: chosen }] : []
  return {
    options: [{ value: EVERY, label: 'Every branch' }, ...listed, ...unknown],
    failed: queryPhase(branches) === 'failed',
  }
}

export default function AssetFilters({
  filters,
  fieldErrors,
  onShow,
}: {
  filters: Filters
  fieldErrors: FieldErrors
  /** Change what the address says. Changes not named keep their value. */
  onShow: (changes: Partial<Filters>) => void
}) {
  // The box holds what is being typed and the address holds what was last
  // searched. When the address changes from somewhere else, the box follows.
  const searched = filters.q ?? ''
  const [draft, setDraft] = useState(searched)
  const [lastSearched, setLastSearched] = useState(searched)
  if (searched !== lastSearched) {
    setLastSearched(searched)
    if (searched !== draft.trim()) setDraft(searched)
  }
  useEffect(() => {
    const typed = draft.trim()
    if (typed === searched) return
    const timer = window.setTimeout(() => onShow({ q: typed === '' ? null : typed, page: FIRST_PAGE }), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [draft, searched, onShow])

  const branches = useBranchOptions(filters.branchCode)

  return (
    <form className="mb-md" aria-label="Find units" onSubmit={(event) => event.preventDefault()}>
      <div className="grid gap-md sm:grid-cols-3">
        <TextInput
          id="asset-search"
          label="Search by tag, serial number or model"
          type="search"
          value={draft}
          onChange={setDraft}
          error={fieldErrors.q}
          autoComplete="off"
        />
        <SelectInput
          id="asset-branch"
          label="Branch"
          value={filters.branchCode ?? EVERY}
          onChange={(value) => onShow({ branchCode: value === EVERY ? null : value, page: FIRST_PAGE })}
          options={branches.options}
          error={fieldErrors.branchCode}
          help={branches.failed ? 'The branches could not be read, so only every branch is offered.' : undefined}
        />
        <SelectInput
          id="asset-status"
          label="Status"
          value={filters.status ?? EVERY}
          onChange={(value) =>
            onShow({ status: ASSET_STATUSES.find((status) => status === value) ?? null, page: FIRST_PAGE })
          }
          options={STATUS_OPTIONS}
          error={fieldErrors.status}
        />
      </div>
      <div className="mt-md">
        <ModelPicker
          id="asset-model"
          legend="Only the units of one model"
          searchLabel="Find a model by name or stock code"
          selectLabel="Model to show"
          noChoice="Every model"
          chosenId={filters.modelId ?? EVERY}
          onChoose={(model) => onShow({ modelId: model?.id ?? null, page: FIRST_PAGE })}
          error={fieldErrors.modelId}
        />
      </div>
    </form>
  )
}
