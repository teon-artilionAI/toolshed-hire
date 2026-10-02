/**
 * Tests for the words a failed sign in gets.
 */

import { describe, expect, it } from 'vitest'
import { ApiError } from '../../shared/api-problem'
import { REFUSED_MESSAGE, describeSignInFailure, waitInWords } from './sign-in-failure'

const LOGIN_PATH = '/api/auth/login'

function refusal(status: number, slug: string, retryAfterSeconds: number | null = null): ApiError {
  return new ApiError({
    kind: 'problem',
    status,
    title: 'Refused',
    detail: `Detail written for the log, about ${slug}.`,
    requestPath: LOGIN_PATH,
    problem: {
      type: `https://toolshedhire.co.za/problems/${slug}`,
      title: 'Refused',
      status,
      detail: `Detail written for the log, about ${slug}.`,
    },
    retryAfterSeconds,
  })
}

describe('how long to wait, in words', () => {
  it.each([
    [1, '1 second'],
    [45, '45 seconds'],
    [59, '59 seconds'],
    [60, '1 minute'],
    [61, '2 minutes'],
    [90, '2 minutes'],
    [900, '15 minutes'],
  ])('writes %i seconds as %s', (seconds, words) => {
    expect(waitInWords(seconds)).toBe(words)
  })

  it('does not invent a time when the server named none', () => {
    expect(waitInWords(null)).toBe('a few minutes')
  })
})

describe('a failed sign in', () => {
  it('gets the same sentence for every 401, whatever the server said about it', () => {
    const wrongPassword = describeSignInFailure(refusal(401, 'invalid-credentials'))
    const somethingElse = describeSignInFailure(refusal(401, 'inactive-account'))

    expect(wrongPassword).toEqual({ kind: 'refused', message: REFUSED_MESSAGE })
    expect(somethingElse).toEqual(wrongPassword)
  })

  it('says how long to wait after too many attempts', () => {
    const failure = describeSignInFailure(refusal(429, 'too-many-attempts', 120))

    expect(failure.kind).toBe('wait')
    expect(failure).toHaveProperty('message', expect.stringContaining('Wait 2 minutes'))
  })

  it('is a fault when the API could not be reached', () => {
    const error = new ApiError({
      kind: 'transport',
      status: null,
      title: 'The API could not be reached',
      detail: 'Nothing answered.',
      requestPath: LOGIN_PATH,
    })

    expect(describeSignInFailure(error)).toEqual({ kind: 'fault', error })
  })

  it('is a fault for anything that is not an API error', () => {
    const error = new Error('Something else')

    expect(describeSignInFailure(error)).toEqual({ kind: 'fault', error })
  })
})
