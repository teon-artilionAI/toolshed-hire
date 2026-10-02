/**
 * Tests for sorting a failed booking request into what the screen says.
 *
 * The errors are made the way the client makes them, from a response, so the
 * sorting is checked against the same shape it meets when the application runs.
 */

import { describe, expect, it } from 'vitest'
import { ApiError, errorFromResponse } from '../../shared/api-problem'
import { problemResponse } from '../../test/api-mock'
import { describeBookingFailure, isNotFound } from './booking-refusal'

const PATH = '/api/reservations'

async function failureFrom(response: Response): Promise<ApiError> {
  return errorFromResponse(response, await response.clone().text(), PATH)
}

describe('describeBookingFailure', () => {
  it('passes on the sentence the server wrote for a conflict', async () => {
    const error = await failureFrom(
      problemResponse(409, { slug: 'asset-unavailable', detail: 'The rammer is not free.' }),
    )

    expect(describeBookingFailure(error)).toEqual({ kind: 'conflict', detail: 'The rammer is not free.' })
  })

  it('recognises an account on hold by the type of the problem, and passes on its sentence', async () => {
    const error = await failureFrom(
      problemResponse(403, { slug: 'account-on-hold', detail: 'This account is on hold.' }),
    )

    expect(describeBookingFailure(error)).toEqual({
      kind: 'accountOnHold',
      detail: 'This account is on hold.',
    })
  })

  it('recognises an unverified email address by the type of the problem', async () => {
    const error = await failureFrom(problemResponse(403, { slug: 'email-not-verified' }))

    expect(describeBookingFailure(error)).toEqual({ kind: 'emailNotVerified' })
  })

  it('reads a 422 into one message for each field', async () => {
    const error = await failureFrom(
      problemResponse(422, {
        detail: 'Some details were refused.',
        errors: { fields: { 'body.from': 'The hire has to start today or later.' } },
      }),
    )

    expect(describeBookingFailure(error)).toEqual({
      kind: 'refused',
      detail: 'Some details were refused.',
      fields: { from: 'The hire has to start today or later.' },
    })
  })

  it.each([
    ['a 403 of another type', () => problemResponse(403, { slug: 'authorisation-failure' })],
    ['a fault the API reported', () => problemResponse(500)],
    ['a 404', () => problemResponse(404)],
    ['a conflict with no problem document', () => new Response('nope', { status: 409 })],
  ])('treats %s as a fault, and keeps the error for the reference', async (_what, respond) => {
    const error = await failureFrom(respond())

    expect(describeBookingFailure(error)).toEqual({ kind: 'fault', error })
  })

  it('treats a request that never reached the API as a fault', () => {
    const error = new ApiError({
      kind: 'transport',
      status: null,
      title: 'The API could not be reached',
      detail: 'Nothing answered.',
      requestPath: PATH,
    })

    expect(describeBookingFailure(error)).toEqual({ kind: 'fault', error })
  })

  it('treats anything that is not an API failure as a fault', () => {
    const error = new TypeError('undefined is not a function')

    expect(describeBookingFailure(error)).toEqual({ kind: 'fault', error })
  })
})

describe('isNotFound', () => {
  it('is true for a 404 and for nothing else', async () => {
    expect(isNotFound(await failureFrom(problemResponse(404)))).toBe(true)
    expect(isNotFound(await failureFrom(problemResponse(403)))).toBe(false)
    expect(isNotFound(new Error('no'))).toBe(false)
    expect(isNotFound(null)).toBe(false)
  })
})
