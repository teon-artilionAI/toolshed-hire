/**
 * One row of SC-02 search results.
 *
 * Its job is to answer, for a single model, whether the customer can have
 * it for the dates they picked, branch by branch. The answer from each branch
 * is free or not free. It is never a count, because the API does not send one
 * and a customer is not meant to know how many units a branch holds.
 *
 * When the customer has picked a branch, the API lists only the models that
 * are free there. So a row never has to say that the chosen branch cannot
 * supply it, and it does not try to.
 *
 * The search checks the dates against the longest hire the branches take
 * online. It does not check them against the shortest and longest hire of each
 * model, and the model's own screen does. So a row whose model does not hire
 * for that many days says so here, before the customer opens it.
 */

import { Link } from 'react-router-dom'
import { ArrowRight, CircleAlert } from 'lucide-react'
import type { ModelAvailabilityRow } from '../../shared/api/contract'
import { money } from '../../shared/format'
import { AvailabilityChip } from './catalogue-ui'

export default function SearchResultRow({
  row,
  hireDays,
  detailHref,
}: {
  row: ModelAvailabilityRow
  /** The days in the period that was searched, as the API counted them. */
  hireDays: number
  detailHref: string
}) {
  const { model, branches } = row
  const withinHireLimits = hireDays >= model.minHireDays && hireDays <= model.maxHireDays

  return (
    <li className="card overflow-hidden">
      <div className="flex flex-col sm:flex-row">
        <div
          className="h-2 shrink-0 bg-gradient-to-br from-slate-600 to-slate-800 sm:h-auto sm:w-3"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1 p-lg">
          <p className="font-mono text-xs uppercase tracking-wide text-slate-faint">
            {model.categoryName}
          </p>
          <h3 className="mt-xs text-lg font-semibold text-ink">{model.name}</h3>
          {/* A figure such as R 2 200,00 holds a space, so each one is kept on
              one line. A price split across two lines reads as two numbers. */}
          <p className="mt-xs text-sm text-slate-soft">
            {model.manufacturer}.{' '}
            <span className="tabular whitespace-nowrap">{money(model.dailyRate)}</span> per day,
            deposit <span className="tabular whitespace-nowrap">{money(model.depositAmount)}</span>.
          </p>

          <ul className="mt-md flex flex-wrap gap-sm" aria-label={`${model.name} at each branch`}>
            {branches.map((branch) => (
              <li key={branch.branchCode}>
                <AvailabilityChip branchName={branch.branchName} available={branch.available} />
              </li>
            ))}
          </ul>

          {!withinHireLimits && (
            <p className="mt-md flex items-start gap-sm text-sm text-ink">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                This tool hires for {model.minHireDays} to {model.maxHireDays} days and your dates
                are {hireDays}. Open it to choose a period it allows.
              </span>
            </p>
          )}

          <Link to={detailHref} className="btn-secondary mt-md px-lg">
            See dates and book
            <span className="sr-only">, {model.name}</span>
            <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </li>
  )
}
