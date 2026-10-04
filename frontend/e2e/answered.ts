/**
 * How the specs that answer the API themselves send one answer.
 *
 * Most answers are a body sent with a 200. A write that makes something
 * answers 201 or 202, a refusal answers with a problem document and a status
 * of its own, and a hold has to end some minutes from the moment it is made.
 * So an answer here is a body, an `Answered` with its own status, or a
 * function that works one out when the request arrives. A route with no
 * answer gets a 404, as from a backend that does not have it.
 */

import type { Route } from '@playwright/test'

/** An answer with a status of its own. */
export class Answered {
  readonly status: number
  readonly body: unknown
  readonly contentType: string

  constructor(status: number, body: unknown, contentType = 'application/json') {
    this.status = status
    this.body = body
    this.contentType = contentType
  }
}

/** A refusal the way the API sends one, as a problem document. */
export function problem(status: number, slug: string, detail: string, errors?: Record<string, unknown>): Answered {
  const body = { type: `https://toolshedhire.co.za/problems/${slug}`, title: slug, status, detail, errors }
  return new Answered(status, body, 'application/problem+json')
}

/** The status a route with no answer gets. */
const NOT_THERE = 404

/**
 * Send one answer to a request the page made.
 *
 * @param found What the route answers, or undefined when it has no answer.
 */
export async function fulfil(route: Route, found: unknown): Promise<void> {
  const answer: unknown = typeof found === 'function' ? found() : found
  if (answer === undefined) {
    await route.fulfill({ status: NOT_THERE, contentType: 'application/json', body: '{}' })
    return
  }
  const { status, body, contentType } = answer instanceof Answered ? answer : new Answered(200, answer)
  await route.fulfill({ status, contentType, body: body === null ? '' : JSON.stringify(body) })
}
