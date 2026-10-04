/**
 * The rows of the SC-22 report, one page at a time.
 *
 * The columns are the server's figures for each row, in the order the server
 * sent the rows, which is highest gross contribution first. Nothing is
 * sorted, summed or worked out here. A utilisation the server sent as null is
 * written as "No serviceable days", and a gross contribution below zero keeps
 * its minus sign beside its colour, so the colour never carries it alone.
 *
 * Ten columns do not fit across a phone or a narrow window, and a table that
 * has to be scrolled sideways hides the figure that matters. So below the `lg`
 * width the table is drawn as one block for each row, with every figure on a
 * line of its own and its heading beside it. It is the same table either way,
 * and each part states its role, because changing how a table is displayed
 * can make a browser stop reporting it as one.
 */

import type { ReactNode } from 'react'
import type { ReportFigures, ReportGrouping, ReportRow } from '../../shared/api/contract'
import { isNegativeMoney, money } from '../../shared/format'
import { StatusPill } from '../../shared/ui'
import { ASSET_STATUS_LABEL } from '../counter/counter-labels'
import { GROSS_CONTRIBUTION, GROUPING_LABEL, utilisationWords } from './report-labels'

interface FigureColumn {
  heading: string
  value: (figures: ReportFigures) => string
}

/** The server's figures for a row, in the order the columns are drawn. */
const FIGURE_COLUMNS: readonly FigureColumn[] = [
  { heading: 'Units', value: (row) => String(row.assetCount) },
  { heading: 'Days on hire', value: (row) => String(row.daysOnHire) },
  { heading: 'Serviceable days', value: (row) => String(row.serviceableDays) },
  { heading: 'Utilisation', value: (row) => utilisationWords(row.utilisationPercent) },
  { heading: 'Hire revenue ex VAT', value: (row) => money(row.hireRevenueExVat) },
  { heading: 'Late fees ex VAT', value: (row) => money(row.lateFeesExVat) },
  { heading: 'Damage recovery ex VAT', value: (row) => money(row.damageRecoveryExVat) },
  { heading: 'Repair costs', value: (row) => money(row.repairCosts) },
]

/** What every cell shares. A table cell from `lg` up, and a line of a block below it. */
const CELL_BASE = 'td px-0 py-xs text-left lg:table-cell lg:px-md lg:py-sm'

/** A cell that shows the name of its column beside its value below `lg`. */
const LABELLED_CELL = `${CELL_BASE} flex items-baseline justify-between gap-md`

/** The name of a column, shown only where the headings are not. */
function ColumnName({ children }: { children: ReactNode }) {
  return <span className="shrink-0 text-sm text-slate-soft lg:hidden">{children}</span>
}

/** Where a row sits, under its name. Each grouping says what applies to it. */
function RowDetail({ row, groupBy }: { row: ReportRow; groupBy: ReportGrouping }) {
  if (groupBy === 'asset') {
    return (
      <span className="mt-xs flex flex-col gap-xs text-xs font-normal text-slate-soft">
        {row.modelName !== null && <span>{row.modelName}</span>}
        {row.branchCode !== null && <span>At {row.branchCode}</span>}
        {row.status !== null && (
          <span>
            <StatusPill status={row.status} label={ASSET_STATUS_LABEL[row.status]} />
          </span>
        )}
      </span>
    )
  }
  if (groupBy === 'model' && row.categoryName !== null) {
    return <span className="mt-xs block text-xs font-normal text-slate-soft">{row.categoryName}</span>
  }
  return null
}

function ReportLine({ row, groupBy }: { row: ReportRow; groupBy: ReportGrouping }) {
  const belowZero = isNegativeMoney(row.grossContribution)
  return (
    <tr role="row" className="block px-md py-sm lg:table-row">
      <th role="rowheader" scope="row" className={`${CELL_BASE} block font-medium text-ink`}>
        <span className={`break-words ${groupBy === 'asset' ? 'font-mono' : ''}`}>{row.label}</span>
        <RowDetail row={row} groupBy={groupBy} />
      </th>
      {FIGURE_COLUMNS.map((column) => (
        <td key={column.heading} role="cell" className={LABELLED_CELL}>
          <ColumnName>{column.heading}</ColumnName>
          <span className="tabular text-right text-ink lg:text-left">{column.value(row)}</span>
        </td>
      ))}
      <td role="cell" className={LABELLED_CELL}>
        <ColumnName>{GROSS_CONTRIBUTION}</ColumnName>
        <span
          className={`tabular text-right font-semibold lg:text-left ${belowZero ? 'text-status-overdue' : 'text-ink'}`}
        >
          {money(row.grossContribution)}
          {belowZero && <span className="block text-xs font-normal">Below zero</span>}
        </span>
      </td>
    </tr>
  )
}

export default function ReportTable({
  rows,
  groupBy,
  caption,
}: {
  rows: readonly ReportRow[]
  groupBy: ReportGrouping
  /** Says what the table holds, for a screen reader. */
  caption: string
}) {
  const headings = [GROUPING_LABEL[groupBy], ...FIGURE_COLUMNS.map((column) => column.heading), GROSS_CONTRIBUTION]
  return (
    <div className="table-wrap">
      <table role="table" className="block w-full border-collapse lg:table">
        <caption className="sr-only">{caption}</caption>
        <thead role="rowgroup" className="hidden border-b border-line bg-muted lg:table-header-group">
          <tr role="row">
            {headings.map((heading) => (
              <th key={heading} role="columnheader" scope="col" className="th whitespace-normal">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup" className="block divide-y divide-line lg:table-row-group">
          {rows.map((row) => (
            <ReportLine key={row.key} row={row} groupBy={groupBy} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
