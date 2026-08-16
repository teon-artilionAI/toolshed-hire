/**
 * Rolling the per unit figures up, and getting them out as a spreadsheet.
 *
 * The owner asked the same question at five levels: how is this unit doing,
 * how is this model doing, this category, this branch, this month. That is
 * one calculation and four groupings, not five reports, so the grouping
 * lives here and the screen only chooses which one to show.
 */

import type { BranchCode } from '../../shared/types'
import type { AssetMetric, ReportPeriod } from './report-metrics'

export type GroupBy = 'asset' | 'model' | 'category' | 'branch'

export const GROUP_OPTIONS: { id: GroupBy; label: string }[] = [
  { id: 'asset', label: 'Individual unit' },
  { id: 'model', label: 'Model' },
  { id: 'category', label: 'Category' },
  { id: 'branch', label: 'Branch' },
]

export const GROUP_COLUMN_HEADING: Record<GroupBy, string> = {
  asset: 'Asset tag',
  model: 'Model',
  category: 'Category',
  branch: 'Branch',
}

/** A row on the report, whichever level it is grouped at. */
export interface ReportRow {
  key: string
  label: string
  sublabel: string
  units: number
  daysOnHire: number
  daysAvailable: number
  utilisation: number
  hireIncome: number
  lateFees: number
  repairCostCarried: number
  grossContribution: number
}

const BRANCH_NAME: Record<BranchCode, string> = {
  CBD: 'Cape Town CBD',
  BEL: 'Bellville',
  SOM: 'Somerset West',
}

export function branchName(code: BranchCode): string {
  return BRANCH_NAME[code]
}

/** Utilisation reads as a whole percentage. Nobody at a counter needs the
 *  decimal, and the CSV carries one for anybody who does. */
export function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

function toRow(
  key: string,
  label: string,
  sublabel: string,
  group: AssetMetric[],
): ReportRow {
  const sum = (pick: (m: AssetMetric) => number) =>
    group.reduce((total, m) => total + pick(m), 0)
  const daysOnHire = sum((m) => m.daysOnHire)
  const daysAvailable = sum((m) => m.daysAvailable)
  return {
    key,
    label,
    sublabel,
    units: group.length,
    daysOnHire,
    daysAvailable,
    utilisation: daysAvailable > 0 ? daysOnHire / daysAvailable : 0,
    hireIncome: sum((m) => m.hireIncome),
    lateFees: sum((m) => m.lateFees),
    repairCostCarried: sum((m) => m.repairCostCarried),
    grossContribution: sum((m) => m.grossContribution),
  }
}

export function groupMetrics(
  metrics: AssetMetric[],
  groupBy: GroupBy,
): ReportRow[] {
  if (groupBy === 'asset') {
    return metrics.map((m) =>
      toRow(m.assetId, m.tag, `${m.modelName}, ${BRANCH_NAME[m.branchCode]}`, [m]),
    )
  }

  const buckets = new Map<string, AssetMetric[]>()
  for (const metric of metrics) {
    const key =
      groupBy === 'model'
        ? metric.modelId
        : groupBy === 'category'
          ? metric.categoryId
          : metric.branchCode
    const bucket = buckets.get(key)
    if (bucket) bucket.push(metric)
    else buckets.set(key, [metric])
  }

  return [...buckets.entries()].map(([key, group]) => {
    const first = group[0]
    const units = `${group.length} ${group.length === 1 ? 'unit' : 'units'}`
    if (groupBy === 'model') {
      return toRow(key, first.modelName, `${first.categoryName}, ${units}`, group)
    }
    if (groupBy === 'category') {
      return toRow(key, first.categoryName, `${units} across the fleet`, group)
    }
    return toRow(key, BRANCH_NAME[first.branchCode], `${units} on site`, group)
  })
}

export type SortKey = 'label' | 'utilisation' | 'grossContribution' | 'daysOnHire'

export const SORT_OPTIONS: { id: SortKey; label: string }[] = [
  { id: 'grossContribution', label: 'Gross contribution, highest first' },
  { id: 'utilisation', label: 'Utilisation, busiest first' },
  { id: 'daysOnHire', label: 'Days on hire, most first' },
  { id: 'label', label: 'Name, A to Z' },
]

export function sortRows(rows: ReportRow[], key: SortKey): ReportRow[] {
  const sorted = [...rows]
  if (key === 'label') sorted.sort((a, b) => a.label.localeCompare(b.label))
  else sorted.sort((a, b) => b[key] - a[key])
  return sorted
}

/** Totals for whatever survived the filters, so the footer matches the body. */
export function totalsOf(metrics: AssetMetric[]): ReportRow {
  return toRow('total', 'Total', '', metrics)
}

/** Units that earned nothing at all in the period. Not knowing which units
 *  these are is the client's third pain point. */
export function idleUnits(metrics: AssetMetric[]): AssetMetric[] {
  return metrics.filter((m) => m.daysOnHire === 0)
}

const CSV_HEADINGS = [
  'Level',
  'Name',
  'Detail',
  'Units',
  'Days on hire',
  'Days available',
  'Utilisation percent',
  'Hire income',
  'Late fees',
  'Repair cost carried',
  'Gross contribution',
]

function csvCell(value: string | number): string {
  const text = String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** Figures leave as plain numbers, not formatted rand, so a spreadsheet can
 *  add them up without anyone stripping currency symbols first. */
export function rowsToCsv(
  rows: ReportRow[],
  groupBy: GroupBy,
  period: ReportPeriod,
): string {
  const lines = [
    `Toolshed Hire utilisation and gross contribution`,
    `Period,${period.start} to ${period.end} (end exclusive)`,
    `Grouped by,${GROUP_COLUMN_HEADING[groupBy]}`,
    '',
    CSV_HEADINGS.join(','),
    ...rows.map((row) =>
      [
        GROUP_COLUMN_HEADING[groupBy],
        row.label,
        row.sublabel,
        row.units,
        row.daysOnHire,
        row.daysAvailable,
        (row.utilisation * 100).toFixed(1),
        row.hireIncome.toFixed(2),
        row.lateFees.toFixed(2),
        row.repairCostCarried.toFixed(2),
        row.grossContribution.toFixed(2),
      ]
        .map(csvCell)
        .join(','),
    ),
  ]
  return lines.join('\r\n')
}

/** Hands the browser a file. No back end is involved, which is the point. */
export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
