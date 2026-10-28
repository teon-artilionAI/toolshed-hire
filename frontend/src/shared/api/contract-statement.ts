/**
 * The statement and data export wire types.
 *
 * The statement is generated from the OpenAPI document, so a route or a field
 * the backend changes stops this compiling. The export is a file download and
 * the document describes it as free-form JSON, so its shape is written here
 * with the version the server stamps on it. Nothing in the application invents
 * a figure or a table name; the server owns both.
 */

import type { IsoTimestamp, JsonOf, Paths, QueryOf } from './contract-kit'

/** The query `GET /api/me/statement` accepts. The period is half open. */
export type MyStatementQuery = QueryOf<Paths['/api/me/statement']['get']>

/** One customer's statement for a period, as `GET /api/me/statement` returns it. */
export type MyStatement = JsonOf<Paths['/api/me/statement']['get']>

/** One hire on a statement. */
export type MyStatementLine = MyStatement['items'][number]

/** One money line on a statement. */
export type MyStatementCharge = MyStatementLine['charges'][number]

/** The figures over every line of a statement. */
export type MyStatementTotals = MyStatement['totals']

/**
 * Everything held about the signed in customer, as `GET /api/me/export`
 * returns it. `tables` is keyed by the table names of the personal data map,
 * and each row is a mapping of column names to JSON values.
 */
export interface MyDataExport {
  formatVersion: string
  generatedAt: IsoTimestamp
  customer: {
    name: string
    email: string
  }
  rowCount: number
  tables: Record<string, Record<string, unknown>[]>
}
