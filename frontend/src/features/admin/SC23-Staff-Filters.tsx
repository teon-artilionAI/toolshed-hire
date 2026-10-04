/**
 * The search and the two filters above the staff accounts on SC-23.
 *
 * The search, the role and whether the account can sign in live in the
 * address under the names the API takes. The search asks a moment after the
 * last key, and the menus apply as they are chosen. A refusal of a filter is
 * put under the control it names.
 */

import { useCallback } from 'react'
import { STAFF_ROLES } from '../../shared/api/admin-users'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { SelectInput, TextInput } from '../counter/counter-fields'
import { FIRST_PAGE } from './report-address'
import { STAFF_ROLE_LABEL } from './staff-words'
import type { StaffFilters } from './users-address'
import { useSearchDraft } from './use-search-draft'

const EVERY = ''
const YES = 'yes'
const NO = 'no'

const ROLE_OPTIONS = [
  { value: EVERY, label: 'Every role' },
  ...STAFF_ROLES.map((role) => ({ value: role, label: STAFF_ROLE_LABEL[role] })),
]

const ACTIVE_OPTIONS = [
  { value: EVERY, label: 'Both' },
  { value: YES, label: 'Yes, they can sign in' },
  { value: NO, label: 'No, deactivated' },
]

function activeValue(active: boolean | null): string {
  if (active === null) return EVERY
  return active ? YES : NO
}

export default function StaffFiltersForm({
  filters,
  fieldErrors,
  onShow,
}: {
  filters: StaffFilters
  fieldErrors: FieldErrors
  /** Change what the address says. Changes not named keep their value. */
  onShow: (changes: Partial<StaffFilters>) => void
}) {
  const search = useCallback((words: string | null) => onShow({ q: words, page: FIRST_PAGE }), [onShow])
  const [draft, setDraft] = useSearchDraft(filters.q, search)

  return (
    <form className="mb-md" aria-label="Find staff accounts" onSubmit={(event) => event.preventDefault()}>
      <div className="grid gap-md sm:grid-cols-3">
        <TextInput
          id="staff-search"
          label="Search by name or email"
          type="search"
          value={draft}
          onChange={setDraft}
          error={fieldErrors.q}
          autoComplete="off"
        />
        <SelectInput
          id="staff-role-filter"
          label="Role"
          value={filters.role ?? EVERY}
          onChange={(value) => onShow({ role: STAFF_ROLES.find((role) => role === value) ?? null, page: FIRST_PAGE })}
          options={ROLE_OPTIONS}
          error={fieldErrors.role}
        />
        <SelectInput
          id="staff-active-filter"
          label="Can they sign in?"
          value={activeValue(filters.active)}
          onChange={(value) => onShow({ active: value === EVERY ? null : value === YES, page: FIRST_PAGE })}
          options={ACTIVE_OPTIONS}
          error={fieldErrors.active}
        />
      </div>
    </form>
  )
}
