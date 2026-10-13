/**
 * Tests for the upload of a file as the raw body of a POST, with
 * `XMLHttpRequest` replaced.
 *
 * It must behave as every other call does. The same address, the same token,
 * one renewal and one repeat on a 401 a new token would cure, the server's
 * refusal as an `ApiError` carrying its sentence and its request id, and a
 * failure to reach the server or to answer in time as a transport failure.
 * Progress is reported as the browser reports it, and a caller can abandon
 * the upload.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { isApiError, malformedResponse } from '../api-problem'
import { failureOf } from '../../test/session-samples'
import { heldOpen, keptAnswer, mockUploads, refusedAnswer } from '../../test/upload-mock'
import { registerAccessTokenProvider, registerSessionRefresher } from './session-seam'
import { UPLOAD_TIMEOUT_MS, uploadFile } from './photo-upload'

const ENDPOINT = '/things/1/photos'
const OLD_TOKEN = 'old-token'
const NEW_TOKEN = 'new-token'
const FILE = new File([new Uint8Array(400)], 'plate.jpg', { type: 'image/jpeg' })

interface Kept {
  id: string
}

function readKept(body: unknown, requestPath: string): Kept {
  if (typeof body === 'object' && body !== null && 'id' in body && typeof body.id === 'string') return { id: body.id }
  throw malformedResponse(requestPath, `Expected an id from ${requestPath}.`)
}

afterEach(() => {
  registerAccessTokenProvider(null)
  registerSessionRefresher(null)
})

describe('an upload the server keeps', () => {
  it('goes to the relative path with the token, the media type and the bytes, and reports progress', async () => {
    registerAccessTokenProvider(() => OLD_TOKEN)
    const uploads = mockUploads(() => keptAnswer({ id: 'kept-1' }, { progress: [100, 400] }))
    const progress = vi.fn()

    const kept = await uploadFile(ENDPOINT, FILE, 'image/jpeg', readKept, { onProgress: progress })

    expect(kept).toEqual({ id: 'kept-1' })
    const [sent] = uploads.uploads
    expect(sent.path).toBe('/api/things/1/photos')
    expect(sent.headers).toEqual({
      Accept: 'application/json',
      'Content-Type': 'image/jpeg',
      Authorization: `Bearer ${OLD_TOKEN}`,
    })
    expect(sent.body).toBe(FILE)
    expect(sent.withCredentials).toBe(true)
    expect(sent.timeout).toBe(UPLOAD_TIMEOUT_MS)
    expect(progress.mock.calls).toEqual([[{ sentBytes: 100, totalBytes: 400 }], [{ sentBytes: 400, totalBytes: 400 }]])
  })

  it('sends no token when nobody is signed in', async () => {
    const uploads = mockUploads(() => keptAnswer({ id: 'kept-2' }))

    await uploadFile(ENDPOINT, FILE, 'image/jpeg', readKept)

    expect(uploads.uploads[0].headers.Authorization).toBeUndefined()
  })

  it('refuses a body that is not the shape asked for, as a malformed answer', async () => {
    mockUploads(() => keptAnswer({ name: 'no id' }))

    const error = await failureOf(uploadFile(ENDPOINT, FILE, 'image/jpeg', readKept))

    expect(error.kind).toBe('malformed')
    expect(error.requestId).toBe('req-upload-0201')
  })
})

describe('an upload the server refuses', () => {
  it('carries the sentence, the status, the request id and the wait the server named', async () => {
    const detail = 'We are busy with other photographs. Wait a few seconds and send this one again.'
    mockUploads(() => refusedAnswer(429, detail, 'too-many-attempts', { 'Retry-After': '5' }))

    const error = await failureOf(uploadFile(ENDPOINT, FILE, 'image/jpeg', readKept))

    expect(error.kind).toBe('problem')
    expect(error.status).toBe(429)
    expect(error.detail).toBe(detail)
    expect(error.requestId).toBe('req-upload-problem')
    expect(error.retryAfterSeconds).toBe(5)
  })

  it('renews the session once on a 401 a new token cures, and sends the file again with it', async () => {
    let token = OLD_TOKEN
    const refresher = vi.fn(async () => {
      token = NEW_TOKEN
      return true
    })
    registerAccessTokenProvider(() => token)
    registerSessionRefresher(refresher)
    const uploads = mockUploads((upload) =>
      upload.headers.Authorization === `Bearer ${NEW_TOKEN}`
        ? keptAnswer({ id: 'kept-3' })
        : refusedAnswer(401, 'The token is not valid.', 'authentication-failure'),
    )

    const kept = await uploadFile(ENDPOINT, FILE, 'image/jpeg', readKept)

    expect(kept).toEqual({ id: 'kept-3' })
    expect(refresher).toHaveBeenCalledTimes(1)
    expect(uploads.uploads.map((upload) => upload.headers.Authorization)).toEqual([`Bearer ${OLD_TOKEN}`, `Bearer ${NEW_TOKEN}`])
  })

  it('is never repeated for a refusal a new token would not cure', async () => {
    registerAccessTokenProvider(() => OLD_TOKEN)
    const refresher = vi.fn(async () => true)
    registerSessionRefresher(refresher)
    const uploads = mockUploads(() => refusedAnswer(409, 'This damage report already has 6 photographs.'))

    const error = await failureOf(uploadFile(ENDPOINT, FILE, 'image/jpeg', readKept))

    expect(error.status).toBe(409)
    expect(refresher).not.toHaveBeenCalled()
    expect(uploads.uploads).toHaveLength(1)
  })
})

describe('an upload that gets no answer', () => {
  it('is a transport failure when it never reaches a server', async () => {
    mockUploads(() => ({ status: 'network' }))

    const error = await failureOf(uploadFile(ENDPOINT, FILE, 'image/jpeg', readKept))

    expect(error.kind).toBe('transport')
    expect(error.title).toBe('The API could not be reached')
  })

  it('is a transport failure that says how long it waited when it times out', async () => {
    mockUploads(() => ({ status: 'timeout' }))

    const error = await failureOf(uploadFile(ENDPOINT, FILE, 'image/jpeg', readKept))

    expect(error.kind).toBe('transport')
    expect(error.detail).toBe(`POST /api/things/1/photos was abandoned after ${UPLOAD_TIMEOUT_MS} ms.`)
  })

  it('rejects with an abort, not a failure, when the caller abandons it', async () => {
    const held = heldOpen()
    mockUploads(() => ({ ...keptAnswer({ id: 'never' }), until: held.until }))
    const controller = new AbortController()

    const upload = uploadFile(ENDPOINT, FILE, 'image/jpeg', readKept, { signal: controller.signal })
    controller.abort()
    held.release()

    const thrown = await upload.then(
      () => null,
      (cause: unknown) => cause,
    )
    expect(isApiError(thrown)).toBe(false)
    expect(thrown).toBeInstanceOf(DOMException)
    expect((thrown as DOMException).name).toBe('AbortError')
  })
})
