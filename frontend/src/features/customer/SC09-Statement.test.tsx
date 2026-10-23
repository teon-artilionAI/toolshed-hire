/**
 * Tests for the statement and data export card on SC-09.
 *
 * The network is replaced at `fetch`, and the browser's own saving of a file
 * is replaced at the link it presses. The card reads the statement for the
 * period on screen, saves the CSV under the name the server gave it, and saves
 * the export the same way. A failure is shown with the server's reference and
 * can be tried again.
 */

import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Mock, MockInstance } from 'vitest'
import type { MyStatement } from '../../shared/api/contract'
import { problemResponse } from '../../test/api-mock'
import { PROFILE } from '../../test/account-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { openAccount, withProfile } from './SC09-test-kit'

const STATEMENT_ROUTE = 'GET /api/me/statement'
const CSV_ROUTE = 'GET /api/me/statement.csv'
const EXPORT_ROUTE = 'GET /api/me/export'
const CSV_NAME = 'toolshed-statement-2026-01-01-2026-10-24.csv'
const EXPORT_NAME = 'toolshed-my-data-2026-10-23.json'
const TEMPORARY_ADDRESS = 'blob:toolshed-test/statement'
const CSV_BODY = '# Statement\r\nHire reference,Branch\r\nTSH-H-26-000901,CBD\r\n'
const EXPORT_BODY = '{"formatVersion":"1","tables":{}}'

const STATEMENT: MyStatement = {
  customerName: PROFILE.fullName,
  customerEmail: PROFILE.email,
  from: '2026-01-01',
  to: '2026-10-24',
  generatedAt: '2026-10-23T09:00:00+00:00',
  totals: {
    hireCount: 1,
    chargesTotalIncVat: '795.00',
    depositHeld: '1200.00',
    depositWithheld: '240.00',
    depositRefunded: '960.00',
    balanceDue: '0.00',
  },
  items: [
    {
      rentalId: '11111111-1111-1111-1111-111111111111',
      reference: 'TSH-H-26-000901',
      branchCode: 'CBD',
      branchName: 'Cape Town CBD',
      status: 'SETTLED',
      from: '2026-10-05',
      dueBackOn: '2026-10-08',
      checkedOutAt: '2026-10-05T09:00:00+00:00',
      returnedAt: '2026-10-08T09:00:00+00:00',
      depositHeld: '1200.00',
      depositWithheld: '240.00',
      depositRefunded: '960.00',
      balanceDue: '0.00',
      chargesTotalIncVat: '795.00',
      charges: [
        {
          id: '22222222-2222-2222-2222-222222222222',
          chargeType: 'HIRE',
          description: 'Hire of the unit',
          amountExVat: '555.00',
          vatAmount: '0.00',
          amountIncVat: '555.00',
          status: 'SETTLED',
          raisedAt: '2026-10-05T09:00:00+00:00',
          reversesChargeId: null,
        },
        {
          id: '33333333-3333-3333-3333-333333333333',
          chargeType: 'LATE_FEE',
          description: 'Late fee',
          amountExVat: '240.00',
          vatAmount: '0.00',
          amountIncVat: '240.00',
          status: 'SETTLED',
          raisedAt: '2026-10-08T09:00:00+00:00',
          reversesChargeId: null,
        },
      ],
    },
  ],
}

function fileResponse(body: string, contentType: string, fileName: string): Response {
  return new Response(body, {
    status: 200,
    headers: {
      'Content-Type': contentType,
      'Content-Disposition': `attachment; filename="${fileName}"`,
      'X-Request-ID': 'req-file-0001',
    },
  })
}

let saved: { name: string }[] = []
let presses: MockInstance | null = null

function giveTheBrowserTemporaryAddresses(): void {
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: vi.fn(() => TEMPORARY_ADDRESS),
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    writable: true,
    value: vi.fn(),
  })
}

async function savedContent(): Promise<string> {
  const create = URL.createObjectURL as Mock<(content: Blob) => string>
  const [content] = create.mock.calls[0]
  return content.text()
}

beforeEach(() => {
  giveTheBrowserTemporaryAddresses()
  saved = []
  presses = vi
    .spyOn(HTMLAnchorElement.prototype, 'click')
    .mockImplementation(function press(this: HTMLAnchorElement) {
      saved.push({ name: this.download })
    })
})

afterEach(() => {
  presses?.mockRestore()
})

describe('the statement card', () => {
  it('shows the hires, the charges and the totals the server sent', async () => {
    await openAccount(withProfile(PROFILE, { [STATEMENT_ROUTE]: () => json(STATEMENT) }))

    expect(await screen.findByText('TSH-H-26-000901', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText('Hire of the unit')).toBeVisible()
    expect(screen.getByText('Late fee')).toBeVisible()
    expect(screen.getByText('Hire of the unit').closest('li')).toHaveTextContent(
      /555,00 with VAT, settled/,
    )
    expect(screen.getByLabelText('Your statement')).toHaveTextContent(/1 200,00/)
  })

  it('downloads the statement as a CSV under the server file name', async () => {
    const { user, network } = await openAccount(
      withProfile(PROFILE, {
        [STATEMENT_ROUTE]: () => json(STATEMENT),
        [CSV_ROUTE]: () => fileResponse(CSV_BODY, 'text/csv', CSV_NAME),
      }),
    )
    await screen.findByText('TSH-H-26-000901', {}, SCREEN_WAIT)

    await user.click(screen.getByRole('button', { name: 'Download my statement' }))

    expect(await screen.findByText(`Downloaded ${CSV_NAME}.`, {}, SCREEN_WAIT)).toBeVisible()
    expect(saved).toEqual([{ name: CSV_NAME }])
    expect(await savedContent()).toBe(CSV_BODY)
    const [request] = network.requestsTo(CSV_ROUTE)
    expect(Object.fromEntries(request.query)).toEqual({
      from: expect.any(String),
      to: expect.any(String),
    })
  })

  it('downloads everything held about the customer as a JSON file', async () => {
    const { user } = await openAccount(
      withProfile(PROFILE, {
        [STATEMENT_ROUTE]: () => json(STATEMENT),
        [EXPORT_ROUTE]: () => fileResponse(EXPORT_BODY, 'application/json', EXPORT_NAME),
      }),
    )
    await screen.findByText('TSH-H-26-000901', {}, SCREEN_WAIT)

    await user.click(screen.getByRole('button', { name: 'Download all my data' }))

    expect(await screen.findByText(`Downloaded ${EXPORT_NAME}.`, {}, SCREEN_WAIT)).toBeVisible()
    expect(saved).toEqual([{ name: EXPORT_NAME }])
    expect(await savedContent()).toBe(EXPORT_BODY)
  })

  it('says so when a file cannot be fetched, and can try again', async () => {
    const { user, network } = await openAccount(
      withProfile(PROFILE, {
        [STATEMENT_ROUTE]: () => json(STATEMENT),
        [CSV_ROUTE]: () => problemResponse(500, { requestId: 'req-csv-9' }),
      }),
    )
    await screen.findByText('TSH-H-26-000901', {}, SCREEN_WAIT)

    await user.click(screen.getByRole('button', { name: 'Download my statement' }))
    expect(await screen.findByRole('alert', {}, SCREEN_WAIT)).toHaveTextContent(
      'We could not download your statement',
    )
    expect(saved).toEqual([])

    network.setRoute(CSV_ROUTE, () => fileResponse(CSV_BODY, 'text/csv', CSV_NAME))
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(`Downloaded ${CSV_NAME}.`, {}, SCREEN_WAIT)).toBeVisible()
  })

  it('shows the failed state when the statement cannot be read', async () => {
    await openAccount(
      withProfile(PROFILE, {
        [STATEMENT_ROUTE]: () => problemResponse(500, { requestId: 'req-statement-9' }),
      }),
    )
    expect(await screen.findByRole('alert', {}, SCREEN_WAIT)).toHaveTextContent(
      'req-statement-9',
    )
  })
})

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'req-statement-0001' },
  })
}
