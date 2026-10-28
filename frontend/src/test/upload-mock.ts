/**
 * A stand-in for `XMLHttpRequest`, for tests of the photograph upload.
 *
 * The upload is the one request that does not go through `fetch`, so the
 * stand-in in api-mock.ts never sees it. This replaces `XMLHttpRequest` itself
 * and nothing above it, so a test exercises the real upload, the real cache
 * and the real screen. Each test says how an upload answers, how far it gets
 * before it answers, and whether it waits for the test before it does.
 *
 * The setup file puts the real `XMLHttpRequest` back after each test.
 */

import { vi } from 'vitest'

const PROBLEM_MEDIA_TYPE = 'application/problem+json'
const REQUEST_ID_HEADER = 'X-Request-ID'
const PROBLEM_TYPE_PREFIX = 'https://toolshedhire.co.za/problems/'
const HTTP_CREATED = 201

/** One upload as a test sees it. */
export interface SeenUpload {
  method: string
  path: string
  headers: Record<string, string>
  body: Blob | null
  withCredentials: boolean
  timeout: number
}

/** How an upload answers. */
export interface UploadAnswer {
  /** The status, or `network` for an upload that never reaches a server, or
   *  `timeout` for one the browser gives up on. */
  status: number | 'network' | 'timeout'
  body?: unknown
  headers?: Record<string, string>
  /** The bytes reported sent, one progress event each, before the answer. */
  progress?: number[]
  /** The answer waits for this, so a test can look at the screen mid upload. */
  until?: Promise<unknown>
}

export type UploadHandler = (upload: SeenUpload) => UploadAnswer

export interface UploadMock {
  uploads: SeenUpload[]
  /** Change how an upload answers from now on. */
  setHandler: (handler: UploadHandler) => void
}

/** A 201 with the JSON body, the way the API keeps a photograph. */
export function keptAnswer(body: unknown, extra: Omit<UploadAnswer, 'status' | 'body'> = {}): UploadAnswer {
  return { status: HTTP_CREATED, body, headers: { 'Content-Type': 'application/json', [REQUEST_ID_HEADER]: 'req-upload-0201' }, ...extra }
}

/** A refusal as a problem document, the way the API sends every error. */
export function refusedAnswer(status: number, detail: string, slug = 'test', headers: Record<string, string> = {}): UploadAnswer {
  return {
    status,
    body: { type: `${PROBLEM_TYPE_PREFIX}${slug}`, title: 'Test Problem', status, detail, requestId: 'req-upload-problem' },
    headers: { 'Content-Type': PROBLEM_MEDIA_TYPE, [REQUEST_ID_HEADER]: 'req-upload-problem', ...headers },
  }
}

/** A promise a test settles when it is ready for the upload to answer. */
export function heldOpen(): { until: Promise<unknown>; release: () => void } {
  let release: () => void = () => undefined
  const until = new Promise<unknown>((resolve) => {
    release = () => resolve(undefined)
  })
  return { until, release }
}

interface ProgressLike {
  loaded: number
  total: number
  lengthComputable: boolean
}

/**
 * Replace `XMLHttpRequest` for the rest of the test.
 *
 * @param handler How each upload answers. An upload a test did not expect
 *   answers 501, so the screen says which answer was missing.
 */
export function mockUploads(handler: UploadHandler = () => refusedAnswer(501, 'The test set up no upload.')): UploadMock {
  const uploads: SeenUpload[] = []
  let current = handler

  class FakeXhr {
    upload: { onprogress: ((event: ProgressLike) => void) | null } = { onprogress: null }
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    ontimeout: (() => void) | null = null
    onabort: (() => void) | null = null
    status = 0
    statusText = ''
    responseText = ''
    timeout = 0
    withCredentials = false
    private method = ''
    private path = ''
    private sent: Record<string, string> = {}
    private answered = new Headers()
    private aborted = false

    open(method: string, path: string): void {
      this.method = method
      this.path = path
    }

    setRequestHeader(name: string, value: string): void {
      this.sent[name] = value
    }

    getResponseHeader(name: string): string | null {
      return this.answered.get(name)
    }

    abort(): void {
      this.aborted = true
      this.onabort?.()
    }

    send(body: Blob | null): void {
      const seen: SeenUpload = {
        method: this.method,
        path: this.path,
        headers: { ...this.sent },
        body,
        withCredentials: this.withCredentials,
        timeout: this.timeout,
      }
      uploads.push(seen)
      void this.answer(current(seen), body?.size ?? 0)
    }

    private async answer(answer: UploadAnswer, size: number): Promise<void> {
      await Promise.resolve()
      for (const loaded of answer.progress ?? []) {
        this.upload.onprogress?.({ loaded, total: size, lengthComputable: true })
      }
      if (answer.until !== undefined) await answer.until
      if (this.aborted) return
      if (answer.status === 'network') return this.onerror?.()
      if (answer.status === 'timeout') return this.ontimeout?.()
      this.status = answer.status
      this.answered = new Headers(answer.headers)
      this.responseText = answer.body === undefined ? '' : JSON.stringify(answer.body)
      this.onload?.()
    }
  }

  vi.stubGlobal('XMLHttpRequest', FakeXhr)
  return {
    uploads,
    setHandler: (next) => {
      current = next
    },
  }
}
