/**
 * SC-17 Asset Locator.
 *
 * The client's second complaint, answered directly: staff cannot tell which
 * branch a unit is at without ringing round. Type a tag or a model name and
 * the answer to "where is the plate compactor" is on screen, across all three
 * branches, with what state the unit is in and who has it.
 *
 * Deliberately read only. Nothing here changes anything, which is why it can
 * be used one handed while someone is on the phone.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MapPin, Search, X } from 'lucide-react'
import { branches } from '../../shared/fixtures'
import type { AssetStatus, BranchCode } from '../../shared/types'
import { humanise } from '../../shared/format'
import {
  Card,
  DataTable,
  EmptyState,
  PageHeader,
  StatTile,
  StatusPill,
} from '../../shared/ui'
import { LOCATED_ASSETS } from './SC17-locator-data'

type BranchFilter = 'ALL' | BranchCode
type StateFilter = 'ALL' | AssetStatus

const BRANCH_OPTIONS: { code: BranchFilter; name: string }[] = [
  { code: 'ALL', name: 'All three branches' },
  ...branches.map((branch) => ({ code: branch.code as BranchFilter, name: branch.name })),
]

const STATE_FILTERS: { value: StateFilter; label: string }[] = [
  { value: 'ALL', label: 'Any state' },
  { value: 'AVAILABLE', label: 'On the shelf' },
  { value: 'RESERVED', label: 'Held for a booking' },
  { value: 'ON_HIRE', label: 'Out on hire' },
  { value: 'QUARANTINED', label: 'Quarantined' },
  { value: 'MAINTENANCE', label: 'In the workshop' },
  { value: 'RETIRED', label: 'Retired' },
]

export default function AssetLocator() {
  const [query, setQuery] = useState('')
  const [branchFilter, setBranchFilter] = useState<BranchFilter>('ALL')
  const [stateFilter, setStateFilter] = useState<StateFilter>('ALL')

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return LOCATED_ASSETS.filter((row) => {
      if (branchFilter !== 'ALL' && row.branchCode !== branchFilter) return false
      if (stateFilter !== 'ALL' && row.status !== stateFilter) return false
      if (!needle) return true
      return [row.tag, row.modelLabel, row.categoryName, row.sku]
        .join(' ')
        .toLowerCase()
        .includes(needle)
    }).sort((a, b) => {
      const needleLower = query.trim().toLowerCase()
      const aExact = a.tag.toLowerCase() === needleLower ? 0 : 1
      const bExact = b.tag.toLowerCase() === needleLower ? 0 : 1
      return aExact - bExact || a.tag.localeCompare(b.tag)
    })
  }, [query, branchFilter, stateFilter])

  const onShelf = results.filter((r) => r.status === 'AVAILABLE').length
  const onHire = results.filter((r) => r.status === 'ON_HIRE').length
  const inWorkshop = results.filter(
    (r) => r.status === 'QUARANTINED' || r.status === 'MAINTENANCE',
  ).length

  const filtered = query.trim() !== '' || branchFilter !== 'ALL' || stateFilter !== 'ALL'

  function clearEverything() {
    setQuery('')
    setBranchFilter('ALL')
    setStateFilter('ALL')
  }

  return (
    <>
      <PageHeader
        screenId="SC-17"
        title="Where is it"
        subtitle="Search any asset tag or model across all three branches. Nothing on this screen changes anything, so it is safe to use while you are on the phone."
      />

      <Card className="mb-lg">
        <div className="flex flex-col gap-md">
          <div>
            <label className="field-label" htmlFor="locator-search">
              Asset tag or model
            </label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-sm top-1/2 h-5 w-5 -translate-y-1/2 text-slate-faint"
                aria-hidden="true"
              />
              <input
                id="locator-search"
                type="search"
                className="field-input pl-[2.5rem]"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="TSH-PC-0021, or plate compactor"
                autoComplete="off"
              />
            </div>
            <p className="field-help">
              Part of a tag works too. Searching "compactor" finds every one on
              the fleet.
            </p>
          </div>

          <fieldset className="min-w-0">
            <legend className="field-label">Branch</legend>
            <div className="mt-xs flex flex-wrap gap-sm">
              {BRANCH_OPTIONS.map((option) => {
                const active = branchFilter === option.code
                return (
                  <button
                    key={option.code}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setBranchFilter(option.code)}
                    className={`btn px-md ${
                      active
                        ? 'bg-accent font-semibold text-accent-ink'
                        : 'border border-line bg-surface text-ink hover:bg-muted'
                    }`}
                  >
                    {option.name}
                  </button>
                )
              })}
            </div>
          </fieldset>

          <div className="flex flex-wrap items-end gap-md">
            <div className="min-w-[14rem] flex-1">
              <label className="field-label" htmlFor="locator-state">
                State
              </label>
              <select
                id="locator-state"
                className="field-input cursor-pointer"
                value={stateFilter}
                onChange={(e) => setStateFilter(e.target.value as StateFilter)}
              >
                {STATE_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            {filtered && (
              <button type="button" className="btn-secondary px-md" onClick={clearEverything}>
                <X className="h-4 w-4 shrink-0" aria-hidden="true" />
                Clear the search
              </button>
            )}
          </div>
        </div>
      </Card>

      <p aria-live="polite" className="sr-only">
        {results.length} {results.length === 1 ? 'unit' : 'units'} found
      </p>

      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Units matching" value={results.length} />
        <StatTile label="On the shelf" value={onShelf} tone="good" hint="Can go out today" />
        <StatTile label="Out on hire" value={onHire} hint="With a customer now" />
        <StatTile
          label="Workshop hold"
          value={inWorkshop}
          tone={inWorkshop > 0 ? 'warn' : 'default'}
          hint="Quarantined or in for repair"
        />
      </div>

      {results.length === 0 ? (
        <div className="card">
          <EmptyState
            title="Nothing matches that search"
            body="Check the tag against the plate on the unit, or search by model instead. Widening the branch filter to all three branches often finds it."
            action={
              <button type="button" className="btn-primary px-md" onClick={clearEverything}>
                Clear the search and start again
              </button>
            }
          />
        </div>
      ) : (
        <DataTable
          caption="Every unit matching the search, with its branch and current state"
          columns={['Tag', 'Model', 'Branch', 'State', 'Grade', 'Where it is now']}
        >
          {results.map((row) => (
            <tr key={row.id} className="transition-colors duration-200 hover:bg-muted">
              <th scope="row" className="td whitespace-nowrap font-mono font-medium text-ink">
                {row.tag}
              </th>
              <td className="td text-ink">
                {row.modelLabel}
                {row.meterHours !== undefined && (
                  <span className="tabular block text-xs text-slate-soft">
                    {row.meterHours} hours on the meter
                  </span>
                )}
              </td>
              <td className="td whitespace-nowrap text-ink">
                <span className="flex items-center gap-xs">
                  <MapPin className="h-4 w-4 shrink-0 text-slate-faint" aria-hidden="true" />
                  {row.branchName}
                </span>
              </td>
              <td className="td">
                <StatusPill status={row.status} label={humanise(row.status)} />
              </td>
              <td className="td tabular text-ink">{row.condition}</td>
              <td className="td text-slate-soft">
                {row.whereabouts}
                {row.late && (
                  <Link
                    to="/counter/overdue"
                    className="mt-xs flex min-h-[2.75rem] items-center font-medium text-status-overdue underline"
                  >
                    Overdue, open the worklist
                  </Link>
                )}
              </td>
            </tr>
          ))}
        </DataTable>
      )}
    </>
  )
}
