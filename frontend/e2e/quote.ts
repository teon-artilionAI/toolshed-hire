/**
 * The server's quote, for a spec that checks a price on a screen.
 *
 * A price is worked out in one place, on the server. So a spec does not work
 * one out either. It asks the quote route the question the screen asked and
 * checks that the screen shows the same figures.
 */

import { expect } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

/** What the specs read of a quote, as the quote route sends it. */
export interface QuoteOnTheWire {
  totalIncVat: string
  depositTotal: string
}

/** The question a screen asks the quote route about one model. */
export interface QuoteQuestion {
  slug: string
  from: string
  to: string
  quantity: number
}

/** Ask the quote route, through the same address the page uses. */
export async function quoteFromTheApi(
  request: APIRequestContext,
  { slug, from, to, quantity }: QuoteQuestion,
): Promise<QuoteOnTheWire> {
  const answer = await request.get(
    `/api/catalogue/models/${encodeURIComponent(slug)}/quote?from=${from}&to=${to}&quantity=${quantity}`,
  )
  expect(answer.ok(), `the quote route answered ${answer.status()} for ${slug}`).toBe(true)
  return (await answer.json()) as QuoteOnTheWire
}

/**
 * An amount from the API, as a pattern for how a screen writes it.
 *
 * The API sends "4508.00" and a screen writes "R 4 508,00". The digits are the
 * same and in the same order, so I allow a space between any two of them and
 * either mark before the cents.
 */
export function asShown(amount: string): RegExp {
  const [rand, cents] = amount.split('.')
  return new RegExp(`^R\\s${rand.split('').join('\\s?')}[,.]${cents}$`)
}
