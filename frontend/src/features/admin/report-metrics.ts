/**
 * Derivation behind SC-22.
 *
 * Nothing here is a hardcoded figure. Every number on the report is
 * computed from the fixture rentals, reservations, assets and damage
 * reports, so changing the data changes the report.
 *
 * Two definitions are load bearing and are stated on the screen itself.
 *
 * 1. Days are half open, matching the schema. A hire collected on the 6th
 *    and returned on the 10th is four days, and the unit is free again on
 *    the 10th. A hire collected today and not yet back counts as one day,
 *    because the hire rate is charged per started day.
 *
 * 2. This is gross contribution, not profit. It is hire income plus late
 *    fees, less the repair cost the business itself carries. It carries no
 *    depreciation, no staff cost, no premises cost and no finance cost,
 *    because the system holds none of those.
 */

import {
  TODAY,
  assets,
  categories,
  damageReports,
  productModels,
  rentals,
  reservations,
} from '../../shared/fixtures'
import type { AssetStatus, BranchCode } from '../../shared/types'

const DAY_MS = 86_400_000
/** Far future sentinel, so "still open" spans can use the same overlap maths. */
const FOREVER = '9999-12-31'

function dayOnly(iso: string): string {
  return iso.slice(0, 10)
}

function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Whole days shared by two half open date ranges. ISO dates sort as strings. */
function overlapDays(
  aStart: string,
  aEnd: string,
  bStart: string,
  bEnd: string,
): number {
  const start = aStart > bStart ? aStart : bStart
  const end = aEnd < bEnd ? aEnd : bEnd
  if (end <= start) return 0
  const ms =
    Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)
  return Math.round(ms / DAY_MS)
}

export interface ReportPeriod {
  id: string
  label: string
  /** Inclusive first day. */
  start: string
  /** Exclusive last day, so today is counted in full. */
  end: string
}

const PERIOD_END = addDays(TODAY, 1)

export const REPORT_PERIODS: ReportPeriod[] = [
  { id: 'last7', label: 'Last 7 days', start: addDays(PERIOD_END, -7), end: PERIOD_END },
  { id: 'last30', label: 'Last 30 days', start: addDays(PERIOD_END, -30), end: PERIOD_END },
  { id: 'last90', label: 'Last 90 days', start: addDays(PERIOD_END, -90), end: PERIOD_END },
  { id: 'ytd', label: 'Year to date', start: '2026-01-01', end: PERIOD_END },
]

export const DEFAULT_PERIOD_ID = 'last30'

export function periodById(id: string): ReportPeriod {
  const period = REPORT_PERIODS.find((p) => p.id === id)
  if (!period) {
    throw new Error(
      `Unknown report period "${id}". Valid ids come from REPORT_PERIODS in report-metrics.ts.`,
    )
  }
  return period
}

/** Metrics for one physical unit over one period. */
export interface AssetMetric {
  assetId: string
  tag: string
  status: AssetStatus
  branchCode: BranchCode
  modelId: string
  modelName: string
  categoryId: string
  categoryName: string
  /** Days the unit was physically out, including days it ran late. */
  daysOnHire: number
  /** Days the unit was on the books and could have earned. */
  daysAvailable: number
  utilisation: number
  hireIncome: number
  lateFees: number
  /** Repair the business carried itself, so not recharged to a customer. */
  repairCostCarried: number
  grossContribution: number
}

interface HireSpan {
  assetId: string
  /** Days billed at the contracted hire rate. */
  hireStart: string
  hireEnd: string
  /** Days past the due date, billed at the late fee rate instead. */
  lateStart: string
  lateEnd: string
  ratePerDay: number
  lateFeePerDay: number
}

/**
 * Every period a unit spent out of the yard, taken from the rental items.
 * The rental is the record of what physically left the branch, so it is the
 * honest basis for utilisation. Reservations only say what was intended.
 */
function hireSpans(): HireSpan[] {
  const spans: HireSpan[] = []
  for (const rental of rentals) {
    const reservation = reservations.find((r) => r.id === rental.reservationId)
    for (const item of rental.items) {
      const asset = assets.find((a) => a.id === item.assetId)
      if (!asset) continue
      const model = productModels.find((m) => m.id === asset.productModelId)
      if (!model) continue
      const line = reservation?.lines.find((l) =>
        l.allocatedAssetIds.includes(asset.id),
      )
      const out = dayOnly(rental.collectedAt)
      const back = item.returnedAt ? dayOnly(item.returnedAt) : TODAY
      const hireEnd = back < rental.dueBackOn ? back : rental.dueBackOn
      const lateStart = rental.dueBackOn
      const lateEnd = back > lateStart ? back : lateStart
      spans.push({
        assetId: asset.id,
        hireStart: out,
        hireEnd,
        lateStart,
        lateEnd,
        ratePerDay: line?.ratePerDaySnapshot ?? model.dailyRate,
        lateFeePerDay: model.lateFeePerDay,
      })
    }
  }
  return spans
}

/** Repair the business carried itself, raised inside the period. */
function repairCarried(assetId: string, period: ReportPeriod): number {
  return damageReports
    .filter((d) => d.assetId === assetId && !d.chargeable)
    .filter((d) => {
      const raised = dayOnly(d.raisedAt)
      return raised >= period.start && raised < period.end
    })
    .reduce((sum, d) => sum + (d.actualRepairCost ?? d.estimatedRepairCost), 0)
}

/**
 * One row per unit. Retired units are left out entirely rather than shown at
 * nought per cent, because a retired unit is not idle, it is gone.
 */
export function assetMetrics(period: ReportPeriod): AssetMetric[] {
  const spans = hireSpans()

  return assets
    .filter((asset) => asset.status !== 'RETIRED')
    .map((asset) => {
      const model = productModels.find((m) => m.id === asset.productModelId)
      const category = categories.find((c) => c.id === model?.categoryId)
      const mine = spans.filter((s) => s.assetId === asset.id)

      let hireDays = 0
      let lateDays = 0
      let hireIncome = 0
      let lateFees = 0

      for (const span of mine) {
        const late = overlapDays(
          span.lateStart,
          span.lateEnd,
          period.start,
          period.end,
        )
        let hire = overlapDays(
          span.hireStart,
          span.hireEnd,
          period.start,
          period.end,
        )
        // A hire collected today and not yet back is one started day, and a
        // started day is a charged day.
        const startedInPeriod =
          span.hireStart >= period.start && span.hireStart < period.end
        if (hire === 0 && late === 0 && startedInPeriod) hire = 1

        hireDays += hire
        lateDays += late
        hireIncome += hire * span.ratePerDay
        lateFees += late * span.lateFeePerDay
      }

      const daysAvailable = overlapDays(
        asset.acquiredOn,
        FOREVER,
        period.start,
        period.end,
      )
      const daysOnHire = hireDays + lateDays
      const repairCostCarried = repairCarried(asset.id, period)

      return {
        assetId: asset.id,
        tag: asset.tag,
        status: asset.status,
        branchCode: asset.branchCode,
        modelId: model?.id ?? 'unknown',
        modelName: model?.name ?? 'Unknown model',
        categoryId: category?.id ?? 'unknown',
        categoryName: category?.name ?? 'Uncategorised',
        daysOnHire,
        daysAvailable,
        utilisation: daysAvailable > 0 ? daysOnHire / daysAvailable : 0,
        hireIncome,
        lateFees,
        repairCostCarried,
        grossContribution: hireIncome + lateFees - repairCostCarried,
      }
    })
}

