/**
 * Tests for the "Download CSV" button of SC-22, with the network replaced at
 * `fetch` and the browser's own saving of a file replaced at the link it
 * presses.
 *
 * The button fetches the CSV route through the client, with the token the
 * session holds, for the period and the filters on the screen and every row.
 * The file is saved under the name the server gave it, with the bytes the
 * server sent. A failure is shown, and a second press tries again.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Mock, MockInstance } from 'vitest'
import { neverAnswers, problemResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { CSV_BODY, CSV_FILE_NAME, REPORT_CSV_ROUTE, csvResponse } from '../../test/report-samples'
import { ACCESS_TOKEN, bearerOf } from '../../test/session-samples'
import { findRows, openReport } from './SC22-test-kit'

const TEMPORARY_ADDRESS = 'blob:toolshed-test/report'

interface SavedFile {
  name: string
  href: string
}

let saved: SavedFile[] = []
let presses: MockInstance | null = null

/** jsdom has no temporary addresses for files, so the test gives it one. */
function giveTheBrowserTemporaryAddresses(): void {
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: vi.fn(() => TEMPORARY_ADDRESS) })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: vi.fn() })
}

/** The bytes handed to the browser for the file it saved. */
async function savedContent(): Promise<string> {
  const create = URL.createObjectURL as Mock<(content: Blob) => string>
  const [content] = create.mock.calls[0]
  return content.text()
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
  giveTheBrowserTemporaryAddresses()
  saved = []
  presses = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function press(this: HTMLAnchorElement) {
    saved.push({ name: this.download, href: this.href })
  })
})

afterEach(() => {
  presses?.mockRestore()
})

describe('downloading the CSV', () => {
  it('fetches every row for the period and the filters on the screen, with the token, and saves the server file', async () => {
    const { user, network } = await openReport(
      { [REPORT_CSV_ROUTE]: () => csvResponse() },
      '/admin/reports?from=2026-02-01&to=2026-03-01&groupBy=model&branchCode=CBD&page=2',
    )
    await findRows()

    await user.click(screen.getByRole('button', { name: 'Download CSV' }))

    expect(await screen.findByText(`Downloaded ${CSV_FILE_NAME}.`, {}, SCREEN_WAIT)).toBeVisible()
    const [request] = network.requestsTo(REPORT_CSV_ROUTE)
    expect(Object.fromEntries(request.query)).toEqual({
      from: '2026-02-01',
      to: '2026-03-01',
      groupBy: 'model',
      branchCode: 'CBD',
    })
    expect(bearerOf(request)).toBe(ACCESS_TOKEN)
    expect(request.headers.get('Accept')).toContain('text/csv')
    expect(saved).toEqual([{ name: CSV_FILE_NAME, href: TEMPORARY_ADDRESS }])
    expect(await savedContent()).toBe(CSV_BODY)
  })

  it('is one request for each press, with the button disabled while it runs', async () => {
    const { user, network } = await openReport({ [REPORT_CSV_ROUTE]: neverAnswers })
    await findRows()

    const button = screen.getByRole('button', { name: 'Download CSV' })
    await user.click(button)

    expect(await screen.findByText('Preparing the file.', {}, SCREEN_WAIT)).toBeVisible()
    expect(button).toBeDisabled()
    await user.click(button)
    expect(network.requestsTo(REPORT_CSV_ROUTE)).toHaveLength(1)
    expect(saved).toEqual([])
  })

  it('says so with the reference when the file cannot be fetched, and tries again', async () => {
    const { user, network } = await openReport({
      [REPORT_CSV_ROUTE]: () => problemResponse(500, { requestId: 'req-csv-1' }),
    })
    await findRows()

    await user.click(screen.getByRole('button', { name: 'Download CSV' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not download the CSV')
    expect(within(alert).getByText('req-csv-1')).toBeVisible()
    expect(saved).toEqual([])

    network.setRoute(REPORT_CSV_ROUTE, () => csvResponse())
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(saved).toHaveLength(1))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('refuses a file the server did not name, and saves nothing', async () => {
    const { user } = await openReport({ [REPORT_CSV_ROUTE]: () => csvResponse(null) })
    await findRows()

    await user.click(screen.getByRole('button', { name: 'Download CSV' }))

    expect(await screen.findByRole('alert', {}, SCREEN_WAIT)).toHaveTextContent('We could not download the CSV')
    expect(saved).toEqual([])
  })
})
