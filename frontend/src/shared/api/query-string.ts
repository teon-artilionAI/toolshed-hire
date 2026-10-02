/**
 * The typed query string builder the client uses.
 *
 * A caller describes its query with its own interface from contract.ts, and
 * this writes it out. It is kept apart from the client so the rule about what
 * is left out can be read, and tested, in one small place.
 */

/** What one query parameter may hold. Undefined, null and the empty string all
 *  mean "leave this parameter out". */
export type QueryValue = string | number | boolean | null | undefined

/** A query object whose every member is something a query string can carry. */
export type QueryShape<Query> = { [Name in keyof Query]: QueryValue }

/**
 * Write a query object as a query string.
 *
 * @param query The parameters, typed by the caller's own query interface.
 * @returns A string that starts with `?`, or an empty string when there is
 *   nothing to send. Names and values are percent encoded. Zero and false are
 *   values and are kept.
 */
export function buildQueryString<Query extends QueryShape<Query>>(query?: Query): string {
  if (!query) return ''
  const search = new URLSearchParams()
  for (const name of Object.keys(query) as (keyof Query & string)[]) {
    const value: QueryValue = query[name]
    if (value === undefined || value === null || value === '') continue
    search.append(name, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}
