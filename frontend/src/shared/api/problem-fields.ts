/**
 * Turning a 422 into one message per field.
 *
 * When the API refuses a request because of what was in it, the problem
 * document names each refused field under `errors`. A form wants that as a
 * plain lookup from the field name to the sentence to show under the input, so
 * this is the one place that reads the document and produces it.
 *
 * The API puts the messages one level down, under `errors.fields`, and starts
 * each name with where the value came from, for example `query.to` for a query
 * parameter and `body.email` for a member of the body. A form knows its field
 * as `to` or `email`, so I strip that prefix and a message lands beside the
 * right input. I also accept a flat `errors` keyed by the bare field name, so
 * a document written that way still reads.
 */

import { isApiError } from '../api-problem'
import type { ApiError } from '../api-problem'

/** The status the API uses for a request it understood and refused to accept. */
export const HTTP_UNPROCESSABLE = 422

/**
 * Whether a failed call was the API refusing what was in the request.
 *
 * A refusal is put right by changing a field, and any other failure by trying
 * again, so a form shows the two differently.
 */
export function isRefusal(error: unknown): error is ApiError {
  return isApiError(error) && error.status === HTTP_UNPROCESSABLE
}

/** A message for each refused field, keyed by the bare field name. */
export type FieldErrors = Readonly<Record<string, string>>

/** The member of `errors` the API puts its field messages under. */
const NESTED_FIELDS_KEY = 'fields'

/** Where a value came from. A name that starts with one of these has it removed. */
const LOCATION_PREFIXES: readonly string[] = ['query', 'body', 'path', 'header', 'cookie']

/** Shown when a field was refused and the document gave no sentence for it. */
const FALLBACK_FIELD_MESSAGE = 'This value was not accepted.'

const NO_FIELD_ERRORS: FieldErrors = Object.freeze({})

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** `query.from` becomes `from`. A name with no location prefix is left alone. */
function bareFieldName(name: string): string {
  const [first, ...rest] = name.split('.')
  return rest.length > 0 && LOCATION_PREFIXES.includes(first) ? rest.join('.') : name
}

/** One sentence from whatever the document put against a field. */
function messageFrom(value: unknown): string {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (Array.isArray(value)) {
    const sentences = value.filter(
      (item): item is string => typeof item === 'string' && item.trim() !== '',
    )
    if (sentences.length > 0) return sentences.map((sentence) => sentence.trim()).join(' ')
  }
  return FALLBACK_FIELD_MESSAGE
}

function collect(source: Record<string, unknown>, into: Record<string, string>): void {
  for (const [name, value] of Object.entries(source)) {
    if (name === NESTED_FIELDS_KEY && isPlainObject(value)) {
      collect(value, into)
      continue
    }
    const field = bareFieldName(name)
    // The first message for a field wins, so the result does not depend on how
    // many ways the document chose to say the same thing.
    if (!(field in into)) into[field] = messageFrom(value)
  }
}

/**
 * Read the per field messages out of a failed call.
 *
 * @param error Whatever the call threw.
 * @returns A message for each refused field. Empty when the failure was not a
 *   422 or carried no `errors`, so a caller can always index into the result.
 */
export function fieldErrorsFromProblem(error: unknown): FieldErrors {
  if (!isRefusal(error)) return NO_FIELD_ERRORS
  const errors = error.problem?.errors
  if (!errors) return NO_FIELD_ERRORS
  const fields: Record<string, string> = {}
  collect(errors, fields)
  return fields
}

/**
 * The messages for fields a form has no input for.
 *
 * A form shows a message under the input it belongs to. Anything left over
 * still has to reach the person, so the form lists these in a notice.
 *
 * @param errors The lookup from `fieldErrorsFromProblem`.
 * @param shownFields The field names the form already shows a message under.
 */
export function otherFieldMessages(errors: FieldErrors, shownFields: readonly string[]): string[] {
  return Object.entries(errors)
    .filter(([field]) => !shownFields.includes(field))
    .map(([, message]) => message)
}
