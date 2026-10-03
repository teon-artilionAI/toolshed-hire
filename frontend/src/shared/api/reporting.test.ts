/**
 * Tests for the reporting routes at the level of the call.
 *
 * The readers check every member of the report and the dashboard, so a body
 * that breaks the contract fails with the name of the field. The CSV goes out
 * through the client like any other call, with the token, and is renewed once
 * when the token is refused, and comes back as the bytes and the name the
 * server gave them.
 */

import { afterEach, describe, expect, it } from 'vitest'
import { jsonResponse, mockApi } from '../../test/api-mock'
import {
  ADMIN_DASHBOARD_ROUTE,
  CSV_BODY,
  CSV_FILE_NAME,
  DASHBOARD,
  REPORT,
  REPORT_CSV_ROUTE,
  REPORT_ROUTE,
  UNIT_ROW,
  csvResponse,
} from '../../test/report-samples'
import { bearerOf, failureOf, tokenRefused } from '../../test/session-samples'
import { getAdminDashboard } from './admin-dashboard'
import { registerAccessTokenProvider } from './client'
import { downloadUtilisationCsv, getUtilisationReport } from './reporting'
import { registerSessionRefresher } from './session-seam'

const QUERY = { from: '2026-02-01', to: '2026-03-01', groupBy: 'model', page: 1, pageSize: 20 } as const

afterEach(() => {
  registerAccessTokenProvider(null)
  registerSessionRefresher(null)
})

describe('the report', () => {
  it('reads every member, a utilisation of null and a contribution below zero included', async () => {
    mockApi({ [REPORT_ROUTE]: () => jsonResponse(REPORT) })

    await expect(getUtilisationReport(QUERY)).resolves.toEqual(REPORT)
  })

  it('reads a unit with its state, and a row that leaves out where it does not sit as null', async () => {
    const { assetTag: _tag, branchCode: _branch, ...unplaced } = { ...UNIT_ROW, status: undefined }
    mockApi({ [REPORT_ROUTE]: () => jsonResponse({ ...REPORT, groupBy: 'asset', items: [UNIT_ROW, unplaced] }) })

    const report = await getUtilisationReport({ ...QUERY, groupBy: 'asset' })

    expect(report.items[0].status).toBe('QUARANTINED')
    expect(report.items[1]).toMatchObject({ assetTag: null, branchCode: null, status: null })
  })

  it.each([
    ['money with no decimals', { ...REPORT, totals: { ...REPORT.totals, repairCosts: '12' } }, 'repairCosts'],
    ['a percentage as a number', { ...REPORT, totals: { ...REPORT.totals, utilisationPercent: 15.78 } }, 'utilisationPercent'],
    ['a grouping it does not know', { ...REPORT, groupBy: 'profit' }, 'groupBy'],
    ['a state no unit has', { ...REPORT, items: [{ ...UNIT_ROW, status: 'RESERVED' }] }, 'status'],
    ['no definitions', { ...REPORT, definitions: undefined }, 'definitions'],
  ])('refuses %s, naming the field', async (_what, body, field) => {
    mockApi({ [REPORT_ROUTE]: () => jsonResponse(body) })

    const failure = await failureOf(getUtilisationReport(QUERY))

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain(field)
  })
})

describe('the dashboard', () => {
  it('reads every member', async () => {
    mockApi({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse(DASHBOARD) })

    await expect(getAdminDashboard()).resolves.toEqual(DASHBOARD)
  })

  it('refuses a count that is not a whole number, naming the field', async () => {
    mockApi({ [ADMIN_DASHBOARD_ROUTE]: () => jsonResponse({ ...DASHBOARD, customersOnHold: 1.5 }) })

    const failure = await failureOf(getAdminDashboard())

    expect(failure.detail).toContain('customersOnHold')
  })
})

describe('the CSV', () => {
  it('goes out with the token and comes back as the bytes and the name the server gave them', async () => {
    registerAccessTokenProvider(() => 'owner-token')
    const network = mockApi({ [REPORT_CSV_ROUTE]: () => csvResponse() })

    const file = await downloadUtilisationCsv({ from: '2026-02-01', to: '2026-03-01', groupBy: 'model' })

    expect(file.fileName).toBe(CSV_FILE_NAME)
    expect(await file.content.text()).toBe(CSV_BODY)
    const [request] = network.requests
    expect(bearerOf(request)).toBe('owner-token')
    expect(request.credentials).toBe('include')
    expect(request.query.has('page')).toBe(false)
  })

  it('renews the session once when the token is refused, and asks again with the new one', async () => {
    let token = 'stale-token'
    registerAccessTokenProvider(() => token)
    registerSessionRefresher(async () => {
      token = 'fresh-token'
      return true
    })
    const network = mockApi({
      [REPORT_CSV_ROUTE]: (request) => (bearerOf(request) === 'fresh-token' ? csvResponse() : tokenRefused()),
    })

    const file = await downloadUtilisationCsv({ from: '2026-02-01', to: '2026-03-01', groupBy: 'branch' })

    expect(file.fileName).toBe(CSV_FILE_NAME)
    expect(network.requests.map(bearerOf)).toEqual(['stale-token', 'fresh-token'])
  })

  it('is refused as malformed when the server does not name the file', async () => {
    mockApi({ [REPORT_CSV_ROUTE]: () => csvResponse(null) })

    const failure = await failureOf(downloadUtilisationCsv({ from: '2026-02-01', to: '2026-03-01', groupBy: 'model' }))

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain('Content-Disposition')
    expect(failure.requestId).toBe('req-test-csv')
  })
})
