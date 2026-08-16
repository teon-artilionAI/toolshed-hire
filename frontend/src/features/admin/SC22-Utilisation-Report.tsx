/**
 * SC-22, Utilisation and Gross Contribution.
 *
 * This is the screen that answers the client's third pain point: nobody can
 * say which units earn their keep. It reports days on hire against days
 * owned, and income against the repair cost the business carries, at four
 * levels of detail and over four periods, and it hands the whole thing over
 * as a spreadsheet.
 *
 * It is deliberately called gross contribution and never profitability. The
 * system holds no depreciation, no staff cost, no premises cost and no
 * finance cost, so a figure labelled profit would be a figure that is not
 * true. The wording of that limit is on the screen, not buried in a manual.
 */

import { useEffect, useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import { money } from '../../shared/format'
import { Card, Notice, PageHeader, StatTile } from '../../shared/ui'
import { DEFAULT_PERIOD_ID, assetMetrics, periodById } from './report-metrics'
import {
  GROUP_COLUMN_HEADING,
  downloadCsv,
  groupMetrics,
  idleUnits,
  percent,
  rowsToCsv,
  sortRows,
  totalsOf,
} from './report-grouping'
import ReportFilters from './ReportFilters'
import type { ReportFilterState } from './ReportFilters'
import ReportTable, { TableSkeleton } from './ReportTable'
import ReportNotes from './ReportNotes'

/** Long enough that the report visibly recalculates, short enough that it
 *  never feels like waiting. Real figures will come from an endpoint. */
const RECALCULATE_MS = 220

const INITIAL_FILTERS: ReportFilterState = {
  periodId: DEFAULT_PERIOD_ID,
  groupBy: 'model',
  branchCode: 'ALL',
  categoryId: 'ALL',
  sortKey: 'grossContribution',
}

export default function UtilisationReport() {
  const [filters, setFilters] = useState<ReportFilterState>(INITIAL_FILTERS)
  const [calculating, setCalculating] = useState(false)
  const [exported, setExported] = useState<string | null>(null)

  const period = periodById(filters.periodId)

  const metrics = useMemo(() => {
    return assetMetrics(period).filter(
      (m) =>
        (filters.branchCode === 'ALL' || m.branchCode === filters.branchCode) &&
        (filters.categoryId === 'ALL' || m.categoryId === filters.categoryId),
    )
  }, [period, filters.branchCode, filters.categoryId])

  const rows = useMemo(
    () => sortRows(groupMetrics(metrics, filters.groupBy), filters.sortKey),
    [metrics, filters.groupBy, filters.sortKey],
  )
  const total = useMemo(() => totalsOf(metrics), [metrics])
  const idle = useMemo(() => idleUnits(metrics), [metrics])
  const statusOf = useMemo(
    () => new Map(metrics.map((m) => [m.assetId, m.status])),
    [metrics],
  )

  useEffect(() => {
    setCalculating(true)
    setExported(null)
    const timer = window.setTimeout(() => setCalculating(false), RECALCULATE_MS)
    return () => window.clearTimeout(timer)
  }, [filters])

  const heading = GROUP_COLUMN_HEADING[filters.groupBy]

  function handleExport() {
    const filename = `toolshed-hire-${filters.groupBy}-${period.start}-to-${period.end}.csv`
    downloadCsv(filename, rowsToCsv(rows, filters.groupBy, period))
    setExported(filename)
  }

  return (
    <>
      <PageHeader
        screenId="SC-22"
        title="Utilisation and gross contribution"
        subtitle={`How hard the fleet worked and what it brought in, ${period.label.toLowerCase()}. Change the breakdown to move between a single unit, a model, a category and a branch.`}
        actions={
          <button
            type="button"
            onClick={handleExport}
            disabled={rows.length === 0}
            className="btn-primary px-md"
          >
            <Download className="h-4 w-4 shrink-0" aria-hidden="true" />
            Export as CSV
          </button>
        }
      />

      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Fleet utilisation"
          value={percent(total.utilisation)}
          hint={`${total.daysOnHire} days out of ${total.daysAvailable} owned`}
        />
        <StatTile
          label="Hire income"
          value={money(total.hireIncome)}
          hint={`${total.units} units counted, retired units left out`}
        />
        <StatTile
          label="Late fees"
          value={money(total.lateFees)}
          tone={total.lateFees > 0 ? 'warn' : 'default'}
          hint="Charged at the model's late fee rate"
        />
        <StatTile
          label="Gross contribution"
          value={money(total.grossContribution)}
          tone={total.grossContribution >= 0 ? 'good' : 'bad'}
          hint={`After ${money(total.repairCostCarried)} of repairs we carried`}
        />
      </div>

      <div className="mb-lg">
        <Card title="Narrow the report down">
          <ReportFilters value={filters} onChange={setFilters} />
        </Card>
      </div>

      {exported && (
        <div className="mb-lg">
          <Notice tone="success" title="Spreadsheet saved to your downloads">
            {exported} holds the {rows.length}{' '}
            {rows.length === 1 ? 'row' : 'rows'} shown below, with figures as
            plain numbers so they add up in a spreadsheet.
          </Notice>
        </div>
      )}

      <div className="mb-lg">
        <Card title={`Broken down by ${heading.toLowerCase()}`}>
          {calculating ? (
            <TableSkeleton />
          ) : (
            <ReportTable
              rows={rows}
              total={total}
              groupBy={filters.groupBy}
              statusOf={statusOf}
              periodLabel={period.label}
              onReset={() => setFilters(INITIAL_FILTERS)}
            />
          )}
        </Card>
      </div>

      <ReportNotes
        idle={idle}
        unitCount={metrics.length}
        periodLabel={period.label}
      />
    </>
  )
}
