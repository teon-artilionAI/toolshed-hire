/**
 * Tests for showing a model to customers and hiding it on SC-20, with the
 * network replaced at `fetch`.
 *
 * Each asks first in words, posts once with the contract's body, says what the
 * model it answered with now is in a notice that takes focus, and reads the
 * list again. A 409 or a 403 shows the server's sentence, and putting the
 * question away gives focus back to its button.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { BREAKER, HAMMER, MODELS_ROUTE, publicationRoute } from '../../test/admin-catalogue-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { lastBody, openCatalogue, rowOf } from './SC20-test-kit'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('publishing and hiding a model', () => {
  it('asks first, then publishes with one request and reads the list again', async () => {
    const { user, network } = await openCatalogue({
      [publicationRoute(BREAKER.id)]: () => jsonResponse({ ...BREAKER, isPublished: true }),
    })
    await user.click(within(await rowOf(BREAKER.name)).getByRole('button', { name: `Publish ${BREAKER.name}` }))

    expect(screen.getByRole('heading', { level: 3, name: `Publish ${BREAKER.name}?` })).toHaveFocus()
    expect(screen.getByText(/book it straight away/)).toBeVisible()
    expect(screen.getByText(/The fleet holds no unit of it yet/)).toBeVisible()
    expect(network.requestsTo(publicationRoute(BREAKER.id))).toHaveLength(0)
    const listReads = network.requestsTo(MODELS_ROUTE).length

    await user.click(screen.getByRole('button', { name: 'Yes, publish it' }))

    expect(await screen.findByText(`${BREAKER.name} is published`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, publicationRoute(BREAKER.id))).toEqual({ published: true })
    expect(screen.getByText(`${BREAKER.name} is published`).closest('[tabindex="-1"]')).toHaveFocus()
    await waitFor(() => expect(network.requestsTo(MODELS_ROUTE).length).toBeGreaterThan(listReads))
  })

  it('asks first, then hides with one request and says bookings already made still stand', async () => {
    const { user, network } = await openCatalogue({
      [publicationRoute(HAMMER.id)]: () => jsonResponse({ ...HAMMER, isPublished: false }),
    })
    await user.click(within(await rowOf(HAMMER.name)).getByRole('button', { name: `Hide ${HAMMER.name}` }))

    expect(screen.getByRole('heading', { level: 3, name: `Hide ${HAMMER.name} from customers?` })).toHaveFocus()
    expect(screen.getByText(/Bookings already made still stand/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Yes, hide it' }))

    expect(await screen.findByText(`${HAMMER.name} is hidden from customers`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, publicationRoute(HAMMER.id))).toEqual({ published: false })
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openCatalogue({ [publicationRoute(HAMMER.id)]: neverAnswers })
    await user.click(within(await rowOf(HAMMER.name)).getByRole('button', { name: `Hide ${HAMMER.name}` }))

    await user.click(screen.getByRole('button', { name: 'Yes, hide it' }))

    const waiting = await screen.findByRole('button', { name: 'Hiding it' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(publicationRoute(HAMMER.id))).toHaveLength(1)
  })

  it.each([
    [409, 'This model is already published.'],
    [403, 'Only the owner can publish a model.'],
  ])('shows the server sentence for a %i', async (status, detail) => {
    const { user } = await openCatalogue({ [publicationRoute(BREAKER.id)]: () => problemResponse(status, { detail }) })
    await user.click(within(await rowOf(BREAKER.name)).getByRole('button', { name: `Publish ${BREAKER.name}` }))

    await user.click(screen.getByRole('button', { name: 'Yes, publish it' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The model was not published')
    expect(alert).toHaveTextContent(detail)
  })

  it('puts the question away and gives focus back to its button', async () => {
    const { user, network } = await openCatalogue()
    await user.click(within(await rowOf(HAMMER.name)).getByRole('button', { name: `Hide ${HAMMER.name}` }))

    await user.click(screen.getByRole('button', { name: 'Keep it as it is' }))

    expect(screen.getByRole('button', { name: `Hide ${HAMMER.name}` })).toHaveFocus()
    expect(network.requestsTo(publicationRoute(HAMMER.id))).toHaveLength(0)
  })
})
