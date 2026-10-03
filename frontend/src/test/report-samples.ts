/**
 * The owner's dashboard and the utilisation report, for tests, shaped the way
 * the contract for the reporting routes describes them.
 *
 * The owner is `ADMIN` from session-samples.ts, and the clock of the tests
 * that use these is pinned to `TEST_NOW`, so today is `TEST_TODAY` and the last
 * full month is February 2026.
 *
 * The figures do not add up on purpose. The totals are not the sum of the
 * rows or of the branches, and no gross contribution is its revenue less its
 * repairs, so a screen that worked a figure out for itself could not arrive
 * at the one the server sent.
 */

import type { AdminDashboard, ReportRow, UtilisationReport } from '../shared/api/contract'
import { TEST_TODAY } from './catalogue-samples'

export const ADMIN_DASHBOARD_ROUTE = 'GET /api/admin/dashboard'
export const REPORT_ROUTE = 'GET /api/admin/reports/utilisation'
export const REPORT_CSV_ROUTE = 'GET /api/admin/reports/utilisation.csv'
export const CATEGORIES_ROUTE = 'GET /api/catalogue/categories'

/** The last full month at `TEST_TODAY`, the way the API counts it. */
export const LAST_FULL_MONTH = { from: '2026-02-01', to: '2026-03-01' }

/** The month so far at `TEST_TODAY`, up to and not including tomorrow. */
export const MONTH_SO_FAR = { from: '2026-03-01', to: '2026-03-13' }

export const DEFINITIONS = {
  utilisation:
    'Utilisation, per asset, for a period, is the days the asset was on an active allocation within the period, divided by the days it was in the fleet and serviceable within the period.',
  grossContribution:
    'Gross contribution, per asset, for a period, is hire revenue excluding VAT plus late fees and damage recovery, less the actual repair costs. It is labelled gross contribution everywhere, never profit.',
}

/** The busiest earner first, the way the server sorts the rows. */
export const HAMMER_ROW: ReportRow = {
  key: 'gbh-2-26-dre-rotary-hammer',
  label: 'Bosch GBH 2-26 DRE rotary hammer',
  branchCode: null,
  categoryName: 'Drilling',
  modelName: 'Bosch GBH 2-26 DRE rotary hammer',
  assetTag: null,
  status: null,
  assetCount: 6,
  daysOnHire: 44,
  serviceableDays: 174,
  utilisationPercent: '25.29',
  hireRevenueExVat: '6160.00',
  lateFeesExVat: '208.70',
  damageRecoveryExVat: '0.00',
  repairCosts: '0.00',
  grossContribution: '6368.70',
}

/** A model whose repairs cost more than it brought in. */
export const COMPACTOR_ROW: ReportRow = {
  ...HAMMER_ROW,
  key: 'cp-100-plate-compactor',
  label: 'CP 100 Plate Compactor',
  categoryName: 'Compaction',
  modelName: 'CP 100 Plate Compactor',
  assetCount: 4,
  daysOnHire: 3,
  serviceableDays: 90,
  utilisationPercent: '3.33',
  hireRevenueExVat: '1020.00',
  lateFeesExVat: '0.00',
  damageRecoveryExVat: '150.00',
  repairCosts: '1450.00',
  grossContribution: '-280.00',
}

/** A model whose only unit spent the month in the workshop. */
export const LADDER_ROW: ReportRow = {
  ...HAMMER_ROW,
  key: 'extension-ladder-7m',
  label: 'Extension ladder 7 m',
  categoryName: 'Ladders, Trestles and Towers',
  modelName: 'Extension ladder 7 m',
  assetCount: 1,
  daysOnHire: 0,
  serviceableDays: 0,
  utilisationPercent: null,
  hireRevenueExVat: '0.00',
  lateFeesExVat: '0.00',
  damageRecoveryExVat: '0.00',
  repairCosts: '0.00',
  grossContribution: '0.00',
}

/** One unit, the way a row reads when the report is grouped by unit. */
export const UNIT_ROW: ReportRow = {
  ...HAMMER_ROW,
  key: 'TSH-DR-0042',
  label: 'TSH-DR-0042',
  branchCode: 'CBD',
  assetTag: 'TSH-DR-0042',
  status: 'QUARANTINED',
  assetCount: 1,
}

/** The report for the last full month, by model, on one page. */
export const REPORT: UtilisationReport = {
  ...LAST_FULL_MONTH,
  groupBy: 'model',
  definitions: DEFINITIONS,
  totals: {
    assetCount: 400,
    daysOnHire: 1834,
    serviceableDays: 11620,
    utilisationPercent: '15.78',
    hireRevenueExVat: '98765.43',
    lateFeesExVat: '1234.56',
    damageRecoveryExVat: '777.77',
    repairCosts: '4321.09',
    grossContribution: '96456.67',
  },
  items: [HAMMER_ROW, COMPACTOR_ROW, LADDER_ROW],
  page: 1,
  pageSize: 20,
  total: 3,
}

/** The report with some of its members replaced. */
export function reportWith(overrides: Partial<UtilisationReport>): UtilisationReport {
  return { ...REPORT, ...overrides }
}

/** The business today. The totals are the server's and are not the sum of the branches. */
export const DASHBOARD: AdminDashboard = {
  date: TEST_TODAY,
  branches: [
    { branchCode: 'CBD', branchName: 'Cape Town CBD', collectionsDue: 2, returnsDue: 1, overdue: 1, onHire: 14, quarantined: 2, underRepair: 0, available: 120 },
    { branchCode: 'BLV', branchName: 'Bellville', collectionsDue: 1, returnsDue: 0, overdue: 0, onHire: 9, quarantined: 1, underRepair: 1, available: 117 },
    { branchCode: 'SMW', branchName: 'Somerset West', collectionsDue: 2, returnsDue: 1, overdue: 0, onHire: 7, quarantined: 0, underRepair: 0, available: 113 },
  ],
  totals: { collectionsDue: 5, returnsDue: 2, overdue: 1, onHire: 31, quarantined: 3, underRepair: 1, available: 351 },
  monthToDate: { ...MONTH_SO_FAR, utilisationPercent: '12.40', grossContribution: '23456.78' },
  openDamageReports: 3,
  customersOnHold: 1,
  failedNotifications: 0,
}

/** The name the CSV route gives the file of the last full month by model. */
export const CSV_FILE_NAME = 'toolshed-gross-contribution-model-2026-02-01-2026-03-01.csv'

/** What the CSV holds, the comment row first. */
export const CSV_BODY =
  '# These are gross contribution figures and not profit.\r\n' +
  'Model,Units,Days on hire,Serviceable days,Utilisation percent,Gross contribution\r\n' +
  'Bosch GBH 2-26 DRE rotary hammer,6,44,174,25.29,6368.70\r\n'

/** A 200 with a CSV body, the way the CSV route sends one. */
export function csvResponse(fileName: string | null = CSV_FILE_NAME, body: string = CSV_BODY): Response {
  const headers: Record<string, string> = { 'Content-Type': 'text/csv; charset=utf-8', 'X-Request-ID': 'req-test-csv' }
  if (fileName !== null) headers['Content-Disposition'] = `attachment; filename="${fileName}"`
  return new Response(body, { status: 200, headers })
}
