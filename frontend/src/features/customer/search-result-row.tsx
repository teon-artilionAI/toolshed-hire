/**
 * One row of SC-02 search results.
 *
 * Its job is to answer, for a single model, whether the customer can have
 * it at the branch they picked for the dates they picked. When the answer
 * is no it says why in the branch's own words and offers the nearest
 * branch that can supply it, because "not available" on its own sends a
 * customer to a competitor.
 */

import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import type { BranchCode } from '../../shared/types'
import { money } from '../../shared/format'
import { Notice } from '../../shared/ui'
import type { BranchAvailability } from './availability'
import { AvailabilityChip } from './catalogue-ui'

export default function SearchResultRow({
  rows,
  here,
  name,
  manufacturer,
  tone,
  categoryName,
  dailyRate,
  deposit,
  detailHref,
  alternative,
  onSwitchBranch,
}: {
  rows: BranchAvailability[]
  here: BranchAvailability | null
  name: string
  manufacturer: string
  tone: string
  categoryName: string
  dailyRate: number
  deposit: number
  detailHref: string
  alternative: BranchAvailability | null
  onSwitchBranch: (code: BranchCode) => void
}) {
  return (
    <li className="card overflow-hidden">
      <div className="flex flex-col sm:flex-row">
        <div
          className={`h-2 shrink-0 bg-gradient-to-br sm:h-auto sm:w-3 ${tone}`}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1 p-lg">
          <p className="font-mono text-xs uppercase tracking-wide text-slate-faint">
            {categoryName}
          </p>
          <h3 className="mt-xs text-lg font-semibold text-ink">{name}</h3>
          <p className="mt-xs text-sm text-slate-soft">
            {manufacturer}. <span className="tabular">{money(dailyRate)}</span> per day,
            deposit <span className="tabular">{money(deposit)}</span>.
          </p>

          <ul className="mt-md flex flex-wrap gap-sm">
            {rows.map((row) => (
              <li key={row.branch.code}>
                <AvailabilityChip row={row} />
              </li>
            ))}
          </ul>

          {here && here.availableUnits === 0 && (
            <div className="mt-md">
              <Notice
                tone={alternative ? 'warn' : 'error'}
                title={
                  here.fleetUnits === 0
                    ? `We do not keep this at ${here.branch.name}`
                    : `Not free at ${here.branch.name} for these dates`
                }
              >
                <p>{here.reason ?? 'Every unit here is committed for the period you asked for.'}</p>
                {alternative ? (
                  <button
                    type="button"
                    className="btn-secondary mt-sm px-md"
                    onClick={() => onSwitchBranch(alternative.branch.code)}
                  >
                    Collect from {alternative.branch.name} instead, {alternative.availableUnits}{' '}
                    free
                  </button>
                ) : (
                  <p className="mt-xs">
                    No other branch has one free either. Open the tool to see the first day it
                    comes back.
                  </p>
                )}
              </Notice>
            </div>
          )}

          <Link to={detailHref} className="btn-secondary mt-md px-lg">
            See the next fourteen days
            <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </li>
  )
}
