/**
 * What the wire types are built with.
 *
 * This is the one module that imports schema.d.ts, which `npm run api:types`
 * generates from the OpenAPI document the backend commits. The contract
 * modules take the generated shapes from here, together with the small type
 * tools that read one operation and the names for the plain values the
 * document can only call a `string`.
 *
 * Nothing outside the contract modules imports this file. The application
 * imports its wire types from contract.ts.
 */

import type { components, paths } from './schema'

/** Every schema the document names, by the name the backend gave it. */
export type Schemas = components['schemas']

/** Every route the document describes, by its path. */
export type Paths = paths

/** The JSON body of the 200 answer of one operation. An operation that has
 *  lost its 200 answer does not satisfy the constraint and stops compiling. */
export type JsonOf<Operation extends { responses: { 200: { content: { 'application/json': unknown } } } }> =
  Operation['responses'][200]['content']['application/json']

/** The JSON body one operation accepts. */
export type BodyOf<Operation extends { requestBody: { content: { 'application/json': unknown } } }> =
  Operation['requestBody']['content']['application/json']

/** The query one operation accepts. */
export type QueryOf<Operation extends { parameters: { query?: object } }> = NonNullable<
  Operation['parameters']['query']
>

/** Writes an intersection out as one plain object type, so an editor shows the
 *  members and not the arithmetic that produced them. */
type Simplify<Shape> = { [Name in keyof Shape]: Shape[Name] }

/**
 * A generated type with some members replaced by more precise ones.
 *
 * The constraint is what keeps this honest. Each member of `Precise` must
 * exist on `Wire` and must be assignable to what `Wire` says it is.
 */
export type Refine<
  Wire,
  Precise extends { [Name in keyof Precise]: Name extends keyof Wire ? Wire[Name] : never },
> = Simplify<Omit<Wire, keyof Precise> & Precise>

/**
 * An amount in rand as the API writes it, for example "280.00".
 *
 * The generated type is a plain `string`, because the document cannot say
 * "two decimals". I keep the name so a money member reads as money. It stays a
 * string all the way to the screen, so no float ever gets a chance to change
 * the figure a customer is shown. `readMoney` checks the two decimals.
 */
export type Money = string

/** A calendar date as the API writes it, `YYYY-MM-DD`. Generated as `string`. */
export type IsoDate = string

/** A time of day as the API writes it, `HH:MM`. Generated as `string`. */
export type ClockTime = string

/** An instant as the API writes it, ISO 8601 with an offset. Generated as `string`. */
export type IsoTimestamp = string
