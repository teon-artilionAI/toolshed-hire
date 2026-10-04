/**
 * Tests for SC-22 Utilisation and Gross Contribution, with the network
 * replaced at `fetch`.
 *
 * The report is one paged request for the period, the grouping and the
 * filters in the address. These tests cover what is asked for, every state of
 * the answer, the figures as the server sent them, and paging. The download
 * is tested in SC22-Report-Download.test.tsx.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { money, percent } from '../../shared/format'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import {
  COMPACTOR_ROW,
  DEFINITIONS,
  HAMMER_ROW,
  LADDER_ROW,
  REPORT,
  REPORT_ROUTE,
  UNIT_ROW,
  reportWith,
} from '../../test/report-samples'
import { findRows, lastAsked, openReport, rowNames } from './SC22-test-kit'

const DEFAULT_ADDRESS = '/admin/reports?from=2026-02-01&to=2026-03-01&groupBy=model'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('what is asked for', () => {
  it('asks for the last full month by model, one page at a time, and writes the period into the address', async () => {
    const { network } = await openReport()
    await findRows()

    const asked = lastAsked(network)
    expect(asked.get('from')).toBe('2026-02-01')
    expect(asked.get('to')).toBe('2026-03-01')
    expect(asked.get('groupBy')).toBe('model')
    expect(asked.get('page')).toBe('1')
    expect(asked.get('pageSize')).toBe('20')
    expect(asked.has('branchCode')).toBe(false)
    expect(asked.has('categorySlug')).toBe(false)
    // The router moves to a new address as a transition, so it lands a moment
    // after the figures. Writing it out asks for nothing new.
    await waitFor(() => expect(currentAddress()).toBe(DEFAULT_ADDRESS))
    expect(network.requestsTo(REPORT_ROUTE)).toHaveLength(1)
  })

  it('asks for what a shared link names, filters and page included', async () => {
    const at = '/admin/reports?from=2026-01-01&to=2026-02-01&groupBy=branch&branchCode=CBD&categorySlug=compaction&page=2'
    const { network } = await openReport({}, at)
    await findRows()

    const asked = lastAsked(network)
    expect(Object.fromEntries(asked)).toEqual({
      from: '2026-01-01',
      to: '2026-02-01',
      groupBy: 'branch',
      branchCode: 'CBD',
      categorySlug: 'compaction',
      page: '2',
      pageSize: '20',
    })
    expect(screen.getByLabelText('Branch')).toHaveValue('CBD')
    expect(screen.getByLabelText('Category')).toHaveValue('compaction')
    expect(screen.getByLabelText('Break the figures down by')).toHaveValue('branch')
  })

  it('falls back to the last full month when the address names no real day', async () => {
    const { network } = await openReport({}, '/admin/reports?from=2026-02-30&to=2026-03-01&groupBy=asset')
    await findRows()

    expect(lastAsked(network).get('from')).toBe('2026-02-01')
    expect(lastAsked(network).get('groupBy')).toBe('asset')
    await waitFor(() => expect(currentAddress()).toBe('/admin/reports?from=2026-02-01&to=2026-03-01&groupBy=asset'))
  })

  it('asks again from the first page when the grouping, a filter or a day changes, and keeps it in the address', async () => {
    const { user, network } = await openReport({}, `${DEFAULT_ADDRESS}&page=3`)
    await findRows()

    await user.selectOptions(screen.getByLabelText('Break the figures down by'), 'branch')
    await waitFor(() => expect(lastAsked(network).get('groupBy')).toBe('branch'))
    expect(lastAsked(network).get('page')).toBe('1')

    await user.selectOptions(screen.getByLabelText('Branch'), 'BLV')
    await waitFor(() => expect(lastAsked(network).get('branchCode')).toBe('BLV'))

    await user.selectOptions(screen.getByLabelText('Category'), 'ladders-trestles-towers')
    await waitFor(() => expect(lastAsked(network).get('categorySlug')).toBe('ladders-trestles-towers'))

    const from = screen.getByLabelText('From')
    await user.clear(from)
    await user.type(from, '2026-01-15')
    await waitFor(() => expect(lastAsked(network).get('from')).toBe('2026-01-15'))
    expect(currentAddress()).toBe(
      '/admin/reports?from=2026-01-15&to=2026-03-01&groupBy=branch&branchCode=BLV&categorySlug=ladders-trestles-towers',
    )
  })

  it('names a child category with its parent', async () => {
    await openReport()

    expect(await screen.findByRole('option', { name: 'Ladders, Trestles and Towers, in Access and Lifting' }, SCREEN_WAIT)).toBeInTheDocument()
  })
})

describe('while the report is worked out', () => {
  it('draws a skeleton and says so, with no sample data notice', async () => {
    await openReport({ [REPORT_ROUTE]: neverAnswers })

    expect(await screen.findByText('Working out the figures.', {}, SCREEN_WAIT)).toBeVisible()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })
})

describe('when the report cannot be read', () => {
  it('says so with the reference, and reads it again on a retry', async () => {
    const { user, network } = await openReport({
      [REPORT_ROUTE]: () => problemResponse(500, { requestId: 'req-report-1' }),
    })

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the report')
    expect(within(alert).getByText('req-report-1')).toBeVisible()

    network.setRoute(REPORT_ROUTE, () => jsonResponse(REPORT))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await findRows()).toBeVisible()
  })

  it('puts a refusal of the period under the field it is about, and lists one it cannot place', async () => {
    await openReport({
      [REPORT_ROUTE]: () =>
        problemResponse(422, {
          errors: { fields: { 'query.to': 'The period may be 366 days at most.', 'query.pageSize': 'Too many rows.' } },
        }),
    })

    const message = await screen.findByText('The period may be 366 days at most.', {}, SCREEN_WAIT)
    const to = screen.getByLabelText('To, not included')
    expect(to).toHaveAttribute('aria-invalid', 'true')
    expect(to.getAttribute('aria-describedby')).toContain(message.closest('p')?.id ?? 'missing')
    const notice = screen.getByRole('alert')
    expect(notice).toHaveTextContent('The report cannot be worked out for that choice')
    expect(within(notice).getByText('Too many rows.')).toBeVisible()
  })

  it('offers to load the branches again when their list fails', async () => {
    const { user, network } = await openReport({ 'GET /api/branches': () => problemResponse(500) })
    await findRows()

    network.setRoute('GET /api/branches', () => jsonResponse({ items: [{ code: 'CBD', name: 'Cape Town CBD', suburb: 'Woodstock', city: 'Cape Town', phone: '021', opensAt: '07:00', closesAt: '17:00' }] }))
    await user.click(screen.getByRole('button', { name: 'Load the branches again' }))

    expect(await screen.findByRole('option', { name: 'Cape Town CBD' }, SCREEN_WAIT)).toBeInTheDocument()
  })
})

describe('a loaded report', () => {
  it('shows both definitions in full and the totals exactly as the server sent them', async () => {
    await openReport()
    await findRows()

    const definitions = screen.getByRole('region', { name: 'What these figures mean' })
    expect(within(definitions).getByText(DEFINITIONS.utilisation)).toBeVisible()
    expect(within(definitions).getByText(DEFINITIONS.grossContribution)).toBeVisible()

    const totals = screen.getByRole('region', { name: 'Totals for the whole report' })
    expect(within(totals).getByText(money('96456.67'))).toBeVisible()
    expect(within(totals).getByText(percent('15.78'))).toBeVisible()
    expect(within(totals).getByText('1834 days on hire of 11620 serviceable days')).toBeVisible()
    expect(within(totals).getByText(money('777.77'))).toBeVisible()
    expect(within(totals).getByText('400')).toBeVisible()
  })

  it('labels the figure gross contribution and never calls anything profit', async () => {
    await openReport()
    await findRows()

    expect(screen.getAllByText('Gross contribution').length).toBeGreaterThan(0)
    expect(screen.getByRole('columnheader', { name: 'Gross contribution' })).toBeInTheDocument()
    for (const mention of screen.getAllByText(/profit/i)) expect(mention.textContent).toMatch(/(not|never) profit/i)
  })

  it('lists the rows in the order the server sent them, with its figures and words for what has none', async () => {
    await openReport()
    await findRows()

    expect(rowNames()).toEqual([HAMMER_ROW.label, COMPACTOR_ROW.label, LADDER_ROW.label])
    const hammer = screen.getByRole('row', { name: new RegExp(HAMMER_ROW.label) })
    expect(within(hammer).getByText(percent('25.29'))).toBeVisible()
    expect(within(hammer).getByText(money('6368.70'))).toBeVisible()
    expect(within(hammer).getByText('Drilling')).toBeVisible()
    const compactor = screen.getByRole('row', { name: new RegExp(COMPACTOR_ROW.label) })
    expect(within(compactor).getByText(money('-280.00'))).toBeVisible()
    expect(within(compactor).getByText('Below zero')).toBeVisible()
    const ladder = screen.getByRole('row', { name: new RegExp(LADDER_ROW.label) })
    expect(within(ladder).getByText('No serviceable days')).toBeVisible()
  })

  it('draws the rows of the page in the chart, and reads every one out in words', async () => {
    await openReport()
    await findRows()

    const chart = screen.getByRole('figure', { name: /Utilisation of each model on this page/ })
    expect(chart).toHaveTextContent(`${HAMMER_ROW.label}, ${percent('25.29')} utilised`)
    expect(chart).toHaveTextContent(`${LADDER_ROW.label}, no serviceable days`)
    expect(chart.querySelectorAll('svg')).toHaveLength(REPORT.items.length)
  })

  it('says the state of each unit in words when the report is grouped by unit', async () => {
    await openReport({ [REPORT_ROUTE]: () => jsonResponse(reportWith({ groupBy: 'asset', items: [UNIT_ROW], total: 1 })) })
    await findRows()

    const unit = screen.getByRole('row', { name: /TSH-DR-0042/ })
    expect(within(unit).getByText('Quarantined until inspected')).toBeVisible()
    expect(within(unit).getByText('At CBD')).toBeVisible()
    expect(screen.getByRole('columnheader', { name: 'Unit' })).toBeInTheDocument()
  })

  it('says when nothing matches, and offers every branch and category again', async () => {
    const { user, network } = await openReport(
      { [REPORT_ROUTE]: () => jsonResponse(reportWith({ items: [], total: 0 })) },
      `${DEFAULT_ADDRESS}&branchCode=SMW`,
    )

    expect(await screen.findByText('Nothing matches that choice', {}, SCREEN_WAIT)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Show every branch and category' }))

    await waitFor(() => expect(lastAsked(network).has('branchCode')).toBe(false))
    expect(currentAddress()).toBe(DEFAULT_ADDRESS)
  })
})

describe('paging', () => {
  it('asks for the next page, keeps it in the address and moves focus to the figures', async () => {
    const { user, network } = await openReport({
      [REPORT_ROUTE]: (request) => jsonResponse(reportWith({ page: Number(request.query.get('page')), total: 45 })),
    })
    await findRows()

    const pages = screen.getByRole('navigation', { name: 'Report pages' })
    expect(within(pages).getByText('Page 1 of 3')).toBeVisible()
    await user.click(within(pages).getByRole('button', { name: /Next/ }))

    await waitFor(() => expect(lastAsked(network).get('page')).toBe('2'))
    expect(currentAddress()).toBe(`${DEFAULT_ADDRESS}&page=2`)
    expect(screen.getByRole('region', { name: 'The figures' })).toHaveFocus()
    expect(await screen.findByText('Page 2 of 3', {}, SCREEN_WAIT)).toBeVisible()
  })

  it('offers the first page when the page asked for is past the end', async () => {
    const { user, network } = await openReport(
      { [REPORT_ROUTE]: (request) => jsonResponse(reportWith({ page: Number(request.query.get('page')), items: request.query.get('page') === '9' ? [] : REPORT.items })) },
      `${DEFAULT_ADDRESS}&page=9`,
    )

    await user.click(await screen.findByRole('button', { name: 'Go to the first page' }, SCREEN_WAIT))

    await waitFor(() => expect(lastAsked(network).get('page')).toBe('1'))
  })
})
