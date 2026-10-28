/**
 * The upload of one file as the raw body of a POST, with its progress.
 *
 * `fetch` cannot say how much of a request body has gone, and a photograph of
 * up to 4 MB sent from a phone at the counter takes long enough that a person
 * needs to see it moving. So this one kind of request goes out through
 * `XMLHttpRequest`, whose upload reports progress. Everything else about it is
 * what client.ts and transport.ts do for every other call. It goes to the same
 * relative base path, carries the same bearer token, renews the session once
 * on a 401 through the same `withSessionRenewal`, logs the same events, and
 * turns a refusal into the same `ApiError`, so a screen shows the server's
 * `detail` exactly as it shows any other refusal.
 *
 * It is never repeated by itself, except once after a renewed session, which
 * the server refused before it looked at the body. A request that timed out
 * may still have stored the file.
 */

import {
  ApiError,
  REQUEST_ID_HEADER,
  RETRY_AFTER_HEADER,
  asApiError,
  errorFromResponse,
  parseJsonBody,
  requestIdFromHeaders,
} from '../api-problem'
import type { BodyReader } from './client'
import { withRequestId } from './client'
import { logEvent } from './log'
import { withSessionRenewal } from './session-seam'
import { apiPath } from './transport'

/** How long an upload may take before it is abandoned. Far longer than a read,
 *  because 4 MB on a weak mobile signal can take most of a minute, and the
 *  server checks and re-encodes the photograph before it answers. */
export const UPLOAD_TIMEOUT_MS = 90_000

const METHOD = 'POST'

/** The response headers the error and the log read. An XMLHttpRequest hands
 *  them over one at a time, so these are copied onto a `Response`. */
const CARRIED_HEADERS = ['Content-Type', REQUEST_ID_HEADER, RETRY_AFTER_HEADER]

const FIRST_GOOD_STATUS = 200
const FIRST_BAD_STATUS = 300

/** How far an upload has got. */
export interface UploadProgress {
  sentBytes: number
  totalBytes: number
}

export interface UploadOptions {
  /** Called each time the browser has sent more of the body. */
  onProgress?: (progress: UploadProgress) => void
  /** Lets the caller abandon the upload, for example when a screen closes. */
  signal?: AbortSignal
}

/** The answer as a `Response`, so the shared readers of an answer can read it. */
function responseOf(xhr: XMLHttpRequest): Response {
  const headers = new Headers()
  for (const name of CARRIED_HEADERS) {
    const value = xhr.getResponseHeader(name)
    if (value !== null) headers.set(name, value)
  }
  return new Response(null, { status: xhr.status, statusText: xhr.statusText, headers })
}

/** The failure for an upload that never got an answer. */
function transportFailure(requestPath: string, timedOut: boolean, bytes: number): ApiError {
  const error = new ApiError({
    kind: 'transport',
    status: null,
    title: timedOut ? 'The API did not answer in time' : 'The API could not be reached',
    detail: timedOut
      ? `${METHOD} ${requestPath} was abandoned after ${UPLOAD_TIMEOUT_MS} ms.`
      : `${METHOD} ${requestPath} never reached a server. The backend is probably not running.`,
    requestPath,
  })
  logEvent('error', 'api.request_failed', {
    method: METHOD,
    path: requestPath,
    kind: error.kind,
    timed_out: timedOut,
    reason: error.detail,
    bytes,
  })
  return error
}

/**
 * Read the answer the upload got, the way client.ts reads any other.
 *
 * @throws ApiError for a refusal, a body that is not JSON, or a body the
 *   reader refuses.
 */
function answerOf<Result>(xhr: XMLHttpRequest, requestPath: string, read: BodyReader<Result>): Result {
  const response = responseOf(xhr)
  const raw = xhr.responseText
  if (xhr.status < FIRST_GOOD_STATUS || xhr.status >= FIRST_BAD_STATUS) {
    const error = errorFromResponse(response, raw, requestPath)
    logEvent('warn', 'api.request_rejected', {
      method: METHOD,
      path: requestPath,
      status: xhr.status,
      kind: error.kind,
      problem_type: error.problem?.type ?? null,
      request_id: error.requestId,
    })
    throw error
  }
  const requestId = requestIdFromHeaders(response)
  try {
    const result = read(parseJsonBody(raw, xhr.status, requestPath, requestId), requestPath)
    logEvent('info', 'api.request_succeeded', { method: METHOD, path: requestPath, status: xhr.status, request_id: requestId })
    return result
  } catch (cause) {
    const error = withRequestId(asApiError(cause, requestPath), requestId)
    logEvent('error', 'api.response_unreadable', {
      method: METHOD,
      path: requestPath,
      status: xhr.status,
      kind: error.kind,
      reason: error.detail,
      request_id: requestId,
    })
    throw error
  }
}

/** Send the file once, with the token given. */
function sendOnce<Result>(
  requestPath: string,
  file: Blob,
  contentType: string,
  read: BodyReader<Result>,
  options: UploadOptions,
  token: string | null,
): Promise<Result> {
  return new Promise<Result>((resolve, reject) => {
    const cancelled = () => new DOMException(`${METHOD} ${requestPath} was cancelled.`, 'AbortError')
    if (options.signal?.aborted) {
      reject(cancelled())
      return
    }
    const xhr = new XMLHttpRequest()
    const forwardAbort = () => xhr.abort()
    const finish = () => options.signal?.removeEventListener('abort', forwardAbort)

    xhr.open(METHOD, requestPath)
    xhr.timeout = UPLOAD_TIMEOUT_MS
    // Same origin by construction, as in transport.ts. I state it for the same reason.
    xhr.withCredentials = true
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.setRequestHeader('Content-Type', contentType)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    xhr.upload.onprogress = (event) => {
      options.onProgress?.({ sentBytes: event.loaded, totalBytes: event.lengthComputable ? event.total : file.size })
    }
    xhr.onload = () => {
      finish()
      try {
        resolve(answerOf(xhr, requestPath, read))
      } catch (failure) {
        reject(failure)
      }
    }
    xhr.onerror = () => {
      finish()
      reject(transportFailure(requestPath, false, file.size))
    }
    xhr.ontimeout = () => {
      finish()
      reject(transportFailure(requestPath, true, file.size))
    }
    xhr.onabort = () => {
      finish()
      logEvent('info', 'api.request_cancelled', { method: METHOD, path: requestPath })
      reject(cancelled())
    }
    options.signal?.addEventListener('abort', forwardAbort, { once: true })

    logEvent('info', 'api.request_started', { method: METHOD, path: requestPath, bytes: file.size })
    xhr.send(file)
  })
}

/**
 * POST a file as the raw body, and read the answer into the caller's type.
 *
 * @param endpoint The endpoint below `/api`, for example `/damage-reports/{id}/photos`.
 * @param file The bytes to send, exactly as they are.
 * @param contentType The media type to send them as.
 * @param read Turns the body of a good answer into the type the caller wants.
 * @throws ApiError on a transport failure, a timeout, a refusal, or a body the
 *   reader refuses. An upload the caller abandoned rejects with an
 *   `AbortError`, which is not a failure and must not be shown as one.
 */
export function uploadFile<Result>(
  endpoint: string,
  file: Blob,
  contentType: string,
  read: BodyReader<Result>,
  options: UploadOptions = {},
): Promise<Result> {
  const requestPath = apiPath(endpoint)
  return withSessionRenewal((token) => sendOnce(requestPath, file, contentType, read, options, token), {
    renew: true,
    method: METHOD,
    path: requestPath,
  })
}
