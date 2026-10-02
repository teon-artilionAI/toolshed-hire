/**
 * Tests for how a failed registration or account request is sorted, and for
 * how the token of a link is read out of an address.
 */

import { describe, expect, it } from 'vitest'
import { ApiError, errorFromResponse } from '../../shared/api-problem'
import { RESET_LINK_INVALID, VERIFICATION_LINK_INVALID } from '../../shared/api/account'
import {
  refusedFields,
  resetLinkInvalid,
  throttled,
  verificationLinkInvalid,
} from '../../test/account-samples'
import { problemResponse } from '../../test/api-mock'
import { describeAccountFailure } from './account-failure'
import { readLinkToken } from './use-link-token'

const PATH = '/api/auth/register'

/** The error the client throws for a response, the way it builds one. */
async function failureFrom(response: Response): Promise<ApiError> {
  return errorFromResponse(response, await response.text(), PATH)
}

describe('sorting a failed account request', () => {
  it('reads a 429 as a wait, with the time the API named', async () => {
    expect(describeAccountFailure(await failureFrom(throttled(90)))).toEqual({
      kind: 'wait',
      message: 'There have been too many attempts. Wait 2 minutes and try again.',
    })
  })

  it('says a few minutes when a 429 names no wait', async () => {
    const failure = describeAccountFailure(await failureFrom(problemResponse(429)))

    expect(failure).toMatchObject({ kind: 'wait', message: expect.stringContaining('Wait a few minutes') })
  })

  it('reads a 422 as a refusal, with a sentence for each field by its bare name', async () => {
    const failure = describeAccountFailure(await failureFrom(refusedFields({ email: 'Not an address.' })))

    expect(failure).toEqual({
      kind: 'refused',
      detail: 'The request was not valid.',
      fields: { email: 'Not an address.' },
    })
  })

  it('reads the 400 of a dead link as a dead link, only for the link it was told about', async () => {
    const verification = await failureFrom(verificationLinkInvalid())
    const reset = await failureFrom(resetLinkInvalid())

    expect(describeAccountFailure(verification, VERIFICATION_LINK_INVALID)).toEqual({ kind: 'linkInvalid' })
    expect(describeAccountFailure(reset, RESET_LINK_INVALID)).toEqual({ kind: 'linkInvalid' })
    // A request that carries no link has no dead link to report.
    expect(describeAccountFailure(verification).kind).toBe('fault')
    expect(describeAccountFailure(reset, VERIFICATION_LINK_INVALID).kind).toBe('fault')
  })

  it('reads everything else as a fault and keeps what was thrown', async () => {
    const serverFault = await failureFrom(problemResponse(500))
    const thrown = new TypeError('Failed to fetch')

    expect(describeAccountFailure(serverFault)).toEqual({ kind: 'fault', error: serverFault })
    expect(describeAccountFailure(thrown)).toEqual({ kind: 'fault', error: thrown })
  })
})

describe('reading the token of a link', () => {
  it.each([
    ['#verify=abc123', 'verify', 'abc123'],
    ['verify=abc123', 'verify', 'abc123'],
    ['#reset=a-b_c.d', 'reset', 'a-b_c.d'],
    ['#other=1&verify=abc123', 'verify', 'abc123'],
    ['#verify=a%2Bb%3D', 'verify', 'a+b='],
    ['#verify=a+b', 'verify', 'a+b'],
    ['#verify=50%', 'verify', '50%'],
  ])('finds the token in %j', (hash, name, token) => {
    expect(readLinkToken(hash, name)).toBe(token)
  })

  it.each([
    ['', 'verify'],
    ['#', 'verify'],
    ['#email', 'verify'],
    ['#verify=', 'verify'],
    ['#reset=abc123', 'verify'],
    ['#unverify=abc123', 'verify'],
  ])('finds none in %j', (hash, name) => {
    expect(readLinkToken(hash, name)).toBeNull()
  })
})
