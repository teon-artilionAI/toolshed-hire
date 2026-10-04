/**
 * The API answered by the spec itself, for the owner's dashboard and report.
 *
 * The accessibility scan and the narrow screen check of SC-19, SC-20, SC-21,
 * SC-22 and SC-24 need a signed in owner, a day across three branches, a
 * report with rows, the trail and the log, whose answers are in
 * audit-answers.ts, the catalogue, whose answers are in catalogue-answers.ts,
 * and the asset register, whose answers are in asset-answers.ts. A scan
 * should not depend on what a database happens to hold, and it should run with
 * or without a backend, so these answers stand in for the API. They are
 * shaped the way the API sends them, with long names and large figures, which
 * are what break a layout. The report
 * answers with units when it is asked for units, so the states of units are
 * scanned too.
 */

import { expect } from '@playwright/test'
import type { Page, Route } from '@playwright/test'
import { ASSET_ANSWERS, ASSET_TAG } from './asset-answers.ts'
import { AUDIT_ANSWERS } from './audit-answers.ts'
import { CATALOGUE_ANSWERS, CATALOGUE_MODEL_ID } from './catalogue-answers.ts'
import { dateFromToday } from './hire-dates.ts'

/** The heading of SC-24, on both of its views. */
export const AUDIT_LOG_HEADING = 'Audit and notification log'

/** The heading of SC-20, with the form closed or open. */
export const CATALOGUE_HEADING = 'Catalogue and pricing'

/** The heading of SC-21, with a unit open or not. */
export const ASSET_REGISTER_HEADING = 'Asset register'

/** What the session leaves in web storage once somebody has signed in. Without
 *  it the application does not ask whether there is a session. */
const SESSION_HINT = "window.localStorage.setItem('toolshed.session-hint', 'yes')"

const OWNER = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000005',
  email: 'marius@toolshedhire.co.za',
  fullName: 'Marius Pretorius-Vanderwesthuizen',
  role: 'admin',
  branchCode: null,
  emailVerified: true,
}

const BRANCHES = {
  items: [
    { code: 'CBD', name: 'Cape Town CBD', suburb: 'Woodstock', city: 'Cape Town', phone: '021 555 0142', opensAt: '07:00', closesAt: '17:00' },
    { code: 'BLV', name: 'Bellville', suburb: 'Stikland', city: 'Cape Town', phone: '021 555 0157', opensAt: '07:00', closesAt: '17:00' },
    { code: 'SMW', name: 'Somerset West', suburb: 'Firgrove', city: 'Cape Town', phone: '021 555 0163', opensAt: '07:00', closesAt: '17:00' },
  ],
}

const CATEGORIES = {
  items: [
    { code: 'COMPACTION', name: 'Compaction and Earthmoving', slug: 'compaction', description: '', parentCode: null, sortOrder: 20, modelCount: 2 },
    { code: 'ACCESS', name: 'Ladders, Trestles and Mobile Scaffold Towers', slug: 'ladders-trestles-towers', description: '', parentCode: 'COMPACTION', sortOrder: 61, modelCount: 1 },
  ],
}

function counts(collectionsDue: number, onHire: number, available: number) {
  return { collectionsDue, returnsDue: 12, overdue: 7, onHire, quarantined: 14, underRepair: 9, available }
}

const DASHBOARD = {
  date: dateFromToday(0),
  branches: [
    { branchCode: 'CBD', branchName: 'Cape Town CBD and Foreshore', ...counts(18, 1240, 9120) },
    { branchCode: 'BLV', branchName: 'Bellville and Northern Suburbs', ...counts(11, 980, 8760) },
    { branchCode: 'SMW', branchName: 'Somerset West and Helderberg', ...counts(9, 610, 7340) },
  ],
  totals: counts(38, 2830, 25220),
  monthToDate: { from: dateFromToday(-3), to: dateFromToday(1), utilisationPercent: '12.40', grossContribution: '-1234567.89' },
  openDamageReports: 123,
  customersOnHold: 45,
  failedNotifications: 6,
}

const DEFINITIONS = {
  utilisation:
    'Utilisation, per asset, for a period. The days the asset was on an active allocation within the period, divided by the days it was in the fleet and serviceable within the period. Days quarantined, under repair, lost or retired are left out of the denominator. Days are half open.',
  grossContribution:
    'Gross contribution, per asset, for a period. Hire revenue excluding VAT attributed to that asset, plus late fees and damage recovery charged on it, less the actual repair costs recorded against it. It is labelled gross contribution everywhere, never profit.',
}

function row(key: string, label: string, utilisationPercent: string | null, grossContribution: string, unit: boolean) {
  return {
    key,
    label,
    branchCode: unit ? 'SMW' : null,
    categoryName: 'Compaction and Earthmoving',
    modelName: 'CP 100 Plate Compactor with Water Tank and Wheel Kit',
    assetTag: unit ? key : null,
    status: unit ? 'UNDER_REPAIR' : null,
    assetCount: unit ? 1 : 126,
    daysOnHire: 18342,
    serviceableDays: 116204,
    utilisationPercent,
    hireRevenueExVat: '1234567.89',
    lateFeesExVat: '98765.43',
    damageRecoveryExVat: '45678.90',
    repairCosts: '123456.78',
    grossContribution,
  }
}

function report(groupBy: string) {
  const unit = groupBy === 'asset'
  return {
    from: dateFromToday(-30),
    to: dateFromToday(0),
    groupBy,
    definitions: DEFINITIONS,
    totals: row('total', 'Total', '15.78', '9876543.21', false),
    items: [
      row(unit ? 'TSH-PC-0007' : 'cp-100', 'CP 100 Plate Compactor with Water Tank and Wheel Kit', '25.29', '1155554.44', unit),
      row(unit ? 'TSH-PC-0012' : 'gbh-2-26', 'Bosch GBH 2-26 DRE Professional SDS-plus Rotary Hammer', '3.33', '-12345.67', unit),
      row(unit ? 'TSH-LD-0003' : 'ladder-7m', 'Extension Ladder Seven Metre Aluminium Triple Section', null, '0.00', unit),
    ],
    page: 1,
    pageSize: 20,
    total: 46,
  }
}

async function answerTheApi(route: Route): Promise<void> {
  const request = route.request()
  const address = new URL(request.url())
  const key = `${request.method()} ${address.pathname}`
  const answers: Record<string, unknown> = {
    'POST /api/auth/refresh': { accessToken: 'owner-scan-token', tokenType: 'Bearer', expiresIn: 900, user: OWNER },
    'GET /api/branches': BRANCHES,
    'GET /api/catalogue/categories': CATEGORIES,
    'GET /api/admin/dashboard': DASHBOARD,
    'GET /api/admin/reports/utilisation': report(address.searchParams.get('groupBy') ?? 'model'),
    ...AUDIT_ANSWERS,
    ...CATALOGUE_ANSWERS,
    ...ASSET_ANSWERS,
  }
  const body = answers[key]
  if (body === undefined) {
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    return
  }
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
}

/** The name the CSV answered here is given, and what it holds. */
export const CSV_FILE_NAME = 'toolshed-gross-contribution-model-2026-09-01-2026-10-01.csv'
export const CSV_BODY =
  '"# These are gross contribution figures and not profit. The period is 2026-09-01 up to but not including 2026-10-01. Days are half open, [from, to)."\r\n' +
  'Model,Category,Units,Days on hire,Serviceable days,Utilisation percent,Hire revenue ex VAT,Late fees ex VAT,Damage recovery ex VAT,Repair costs,Gross contribution\r\n' +
  'CP 100 Plate Compactor with Water Tank and Wheel Kit,Compaction and Earthmoving,126,18342,116204,25.29,1234567.89,98765.43,45678.90,123456.78,1155554.44\r\n' +
  "'=Bosch GBH 2-26 DRE,Drilling,4,3,90,3.33,1020.00,0.00,150.00,13495.67,-12345.67\r\n"

/** Answer the CSV route the way the API does. */
export async function answerTheCsv(route: Route): Promise<void> {
  await route.fulfill({
    status: 200,
    headers: {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': `attachment; filename="${CSV_FILE_NAME}"`,
    },
    body: CSV_BODY,
  })
}

/** An owner's screen to open, and what proves it has loaded. */
export interface AdminScreen {
  path: string
  heading: string
  /** Something that is only on the page once the screen has its data. */
  loaded: string
}

export const ADMIN_SCREENS: readonly AdminScreen[] = [
  { path: '/admin', heading: 'Business overview', loaded: 'Branch by branch' },
  { path: '/admin/reports', heading: 'Utilisation and gross contribution', loaded: 'What these figures mean' },
  { path: '/admin/reports?groupBy=asset', heading: 'Utilisation and gross contribution', loaded: 'In the workshop' },
  { path: '/admin/audit', heading: AUDIT_LOG_HEADING, loaded: 'Reservation confirmed' },
  { path: '/admin/audit?view=notifications', heading: AUDIT_LOG_HEADING, loaded: 'What went wrong' },
  { path: '/admin/catalogue', heading: CATALOGUE_HEADING, loaded: 'AC-YOUNGMAN-BOSS-CLIMA' },
  { path: `/admin/catalogue?model=${CATALOGUE_MODEL_ID}`, heading: CATALOGUE_HEADING, loaded: 'Last changed' },
  { path: '/admin/assets', heading: ASSET_REGISTER_HEADING, loaded: ASSET_TAG },
  { path: `/admin/assets?asset=${ASSET_TAG}`, heading: ASSET_REGISTER_HEADING, loaded: 'Held for booking TSH-R-26-000124' },
]

/** Open an owner's screen as the signed in owner, with the API answered here. */
export async function openAdminScreen(page: Page, screen: AdminScreen): Promise<void> {
  await page.addInitScript(SESSION_HINT)
  await page.route('**/api/**', answerTheApi)
  await page.goto(screen.path)
  await expect(page.getByRole('heading', { level: 1, name: screen.heading })).toBeVisible()
  await expect(page.getByText(screen.loaded).first()).toBeVisible()
}
