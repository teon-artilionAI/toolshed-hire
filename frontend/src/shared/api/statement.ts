/**
 * The customer's own statement and data export.
 *
 * Three calls. One reads the statement for a period, so the account screen can
 * show it and print it. One downloads the same statement as a CSV file. One
 * downloads everything held about the customer as a JSON file, through the
 * same client, token and renewal as every other request.
 *
 * Every figure is the server's, and every row is read through a check that
 * refuses a body breaking the contract. Nothing here adds anything up.
 */

import { api } from './client'
import type { ApiFile } from './client'
import type {
  IsoDate,
  IsoTimestamp,
  Money,
  MyStatement,
  MyStatementCharge,
  MyStatementLine,
  MyStatementQuery,
  MyStatementTotals,
} from './contract'
import {
  readCount,
  readDate,
  readList,
  readNullableText,
  readNullableTimestamp,
  readObject,
  readOneOf,
  readSignedMoney,
  readText,
  readTimestamp,
} from './read'

const STATEMENT_ENDPOINT = '/me/statement'
const CSV_ENDPOINT = '/me/statement.csv'
const EXPORT_ENDPOINT = '/me/export'
const CSV_ACCEPT = 'text/csv, application/problem+json'

export const RENTAL_STATUSES = [
  'OPEN',
  'OVERDUE',
  'PARTIALLY_RETURNED',
  'RETURNED',
  'SETTLED',
] as const
export const CHARGE_TYPES = [
  'HIRE',
  'DEPOSIT_HOLD',
  'DEPOSIT_RELEASE',
  'DEPOSIT_FORFEIT',
  'LATE_FEE',
  'DAMAGE_RECOVERY',
  'CLEANING',
  'ADJUSTMENT',
] as const
export const CHARGE_STATUSES = ['PENDING', 'SETTLED', 'WAIVED', 'REVERSED'] as const

function readCharge(value: unknown, path: string): MyStatementCharge {
  const record = readObject(value, path, 'a charge on a statement')
  return {
    id: readText(record, 'id', path),
    chargeType: readOneOf(record, 'chargeType', path, CHARGE_TYPES),
    description: readText(record, 'description', path),
    amountExVat: readSignedMoney(record, 'amountExVat', path),
    vatAmount: readSignedMoney(record, 'vatAmount', path),
    amountIncVat: readSignedMoney(record, 'amountIncVat', path),
    status: readOneOf(record, 'status', path, CHARGE_STATUSES),
    raisedAt: readTimestamp(record, 'raisedAt', path),
    reversesChargeId: readNullableText(record, 'reversesChargeId', path),
  }
}

function readLine(value: unknown, path: string): MyStatementLine {
  const record = readObject(value, path, 'a hire on a statement')
  return {
    rentalId: readText(record, 'rentalId', path),
    reference: readText(record, 'reference', path),
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    status: readOneOf(record, 'status', path, RENTAL_STATUSES),
    from: readDate(record, 'from', path),
    dueBackOn: readDate(record, 'dueBackOn', path),
    checkedOutAt: readTimestamp(record, 'checkedOutAt', path),
    returnedAt: readNullableTimestamp(record, 'returnedAt', path),
    depositHeld: readSignedMoney(record, 'depositHeld', path),
    depositWithheld: readSignedMoney(record, 'depositWithheld', path),
    depositRefunded: readSignedMoney(record, 'depositRefunded', path),
    balanceDue: readSignedMoney(record, 'balanceDue', path),
    chargesTotalIncVat: readSignedMoney(record, 'chargesTotalIncVat', path),
    charges: readList(record, 'charges', path, readCharge),
  }
}

function readTotals(value: unknown, path: string): MyStatementTotals {
  const record = readObject(value, path, 'the totals of a statement')
  return {
    hireCount: readCount(record, 'hireCount', path),
    chargesTotalIncVat: readSignedMoney(record, 'chargesTotalIncVat', path),
    depositHeld: readSignedMoney(record, 'depositHeld', path),
    depositWithheld: readSignedMoney(record, 'depositWithheld', path),
    depositRefunded: readSignedMoney(record, 'depositRefunded', path),
    balanceDue: readSignedMoney(record, 'balanceDue', path),
  }
}

function readStatement(value: unknown, path: string): MyStatement {
  const record = readObject(value, path, 'a statement')
  return {
    customerName: readText(record, 'customerName', path),
    customerEmail: readText(record, 'customerEmail', path),
    from: readDate(record, 'from', path),
    to: readDate(record, 'to', path),
    generatedAt: readTimestamp(record, 'generatedAt', path),
    totals: readTotals(record.totals, path),
    items: readList(record, 'items', path, readLine),
  }
}

/**
 * GET /api/me/statement. The signed in customer's statement for a period.
 *
 * @throws ApiError with status 422 naming `from` or `to` when the period is
 *   reversed or longer than ten years.
 */
export function getMyStatement(
  query: MyStatementQuery,
  signal?: AbortSignal,
): Promise<MyStatement> {
  return api.get(STATEMENT_ENDPOINT, readStatement, { query, signal })
}

/**
 * GET /api/me/statement.csv. The same statement as a file, with the name the
 * server gave it.
 */
export function downloadMyStatementCsv(query: MyStatementQuery): Promise<ApiFile> {
  return api.getFile(CSV_ENDPOINT, CSV_ACCEPT, { query })
}

/**
 * GET /api/me/export. Everything held about the customer as a JSON file.
 *
 * The route answers a file, not JSON the screen renders, so the bytes are kept
 * exactly as they came and handed to the browser under the server's name.
 */
export function downloadMyData(): Promise<ApiFile> {
  return api.getFile(EXPORT_ENDPOINT, 'application/json, application/problem+json')
}

export type StatementPeriod = { from: IsoDate; to: IsoDate }
export type StatementMoney = Money
export type StatementGeneratedAt = IsoTimestamp
