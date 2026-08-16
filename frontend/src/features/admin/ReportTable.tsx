/**
 * The body of the SC-22 report: one table that reads the same whether it is
 * showing a single unit, a model, a category or a branch.
 *
 * Real table markup, a caption for screen readers, a row header per row and
 * a totals row that always matches the rows above it. Wide on purpose, so it
 * scrolls inside its own container rather than pushing the page sideways,
 * which is what DataTable already handles.
 */

import type { AssetStatus } from '../../shared/types'
import { money } from '../../shared/format'
import { DataTable, EmptyState, StatusPill } from '../../shared/ui'
import { GROUP_COLUMN_HEADING, percent } from './report-grouping'
import type { GroupBy, ReportRow } from './report-grouping'

function UtilisationBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const tone =
    pct >= 50
      ? 'bg-status-available'
      : pct >= 20
        ? 'bg-status-due'
        : 'bg-status-overdue'
  return (
    <div className="flex items-center gap-sm">
      <span className="tabular w-10 shrink-0 text-right font-medium">{pct}%</span>
      <span
        aria-hidden="true"
        className="hidden h-2 w-20 shrink-0 overflow-hidden rounded bg-muted sm:block"
      >
        <span
          className={`block h-full rounded ${tone}`}
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </span>
    </div>
  )
}

export function TableSkeleton() {
  return (
    <div>
      <p role="status" className="sr-only">
        Working out the figures
      </p>
      <div className="animate-pulse space-y-md" aria-hidden="true">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-6 w-full rounded bg-muted" />
        ))}
      </div>
    </div>
  )
}

export default function ReportTable({
  rows,
  total,
  groupBy,
  statusOf,
  periodLabel,
  onReset,
}: {
  rows: ReportRow[]
  total: ReportRow
  groupBy: GroupBy
  statusOf: Map<string, AssetStatus>
  periodLabel: string
  onReset: () => void
}) {
  const heading = GROUP_COLUMN_HEADING[groupBy]

  if (rows.length === 0) {
    return (
      <EmptyState
        title="Nothing matches those filters"
        body="No units are on the books for that branch and category together. Widen the branch or the category and the figures will come back."
        action={
          <button type="button" onClick={onReset} className="btn-secondary px-md">
            Reset the filters
          </button>
        }
      />
    )
  }

  return (
    <DataTable
      columns={[
        heading,
        groupBy === 'asset' ? 'Status' : 'Units',
        'Days on hire',
        'Utilisation',
        'Hire income',
        'Late fees',
        'Repair carried',
        'Gross contribution',
      ]}
      caption={`Utilisation and gross contribution by ${heading.toLowerCase()}, ${periodLabel}`}
    >
      {rows.map((row) => {
        const status = statusOf.get(row.key)
        return (
          <tr key={row.key} className="transition-colors duration-200 hover:bg-muted">
            <th scope="row" className="td text-left font-medium text-ink">
              <span className={groupBy === 'asset' ? 'font-mono' : ''}>
                {row.label}
              </span>
              <span className="mt-xs block text-xs font-normal text-slate-soft">
                {row.sublabel}
              </span>
            </th>
            <td className="td">
              {groupBy === 'asset' && status ? (
                <StatusPill status={status} />
              ) : (
                <span className="tabular">{row.units}</span>
              )}
            </td>
            <td className="td tabular">{row.daysOnHire}</td>
            <td className="td">
              <UtilisationBar value={row.utilisation} />
            </td>
            <td className="td tabular font-mono">{money(row.hireIncome)}</td>
            <td className="td tabular font-mono">{money(row.lateFees)}</td>
            <td className="td tabular font-mono">{money(row.repairCostCarried)}</td>
            <td
              className={`td tabular font-mono font-semibold ${
                row.grossContribution < 0 ? 'text-status-overdue' : 'text-ink'
              }`}
            >
              {money(row.grossContribution)}
              {row.grossContribution < 0 && (
                <span className="block text-xs font-normal">Cost us money</span>
              )}
            </td>
          </tr>
        )
      })}
      <tr className="bg-muted font-semibold">
        <th scope="row" className="td text-left">
          Total
        </th>
        <td className="td tabular">{total.units}</td>
        <td className="td tabular">{total.daysOnHire}</td>
        <td className="td tabular">{percent(total.utilisation)}</td>
        <td className="td tabular font-mono">{money(total.hireIncome)}</td>
        <td className="td tabular font-mono">{money(total.lateFees)}</td>
        <td className="td tabular font-mono">{money(total.repairCostCarried)}</td>
        <td className="td tabular font-mono">{money(total.grossContribution)}</td>
      </tr>
    </DataTable>
  )
}
