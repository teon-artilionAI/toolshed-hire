/**
 * Tests for the no show on SC-11, with the network replaced at `fetch`.
 *
 * The diary offers it where the server says it may, asks for the reason and
 * says what will happen, and then sends one request. The tests cover the
 * question, the answer the server gives when it agrees, its refusal with a
 * 409, a reason it refuses, and putting the question away again.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, problemResponse } from '../../test/api-mock'
import type { RouteHandler } from '../../test/api-mock'
import { TEST_NOW, TEST_TODAY } from '../../test/catalogue-samples'
import { THANDI } from '../../test/counter-samples'
import { DIARY_ROUTE, DUE_OUT, MARKED_NO_SHOW, noShowRoute } from '../../test/overview-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { REFERENCE } from '../../test/reservation-samples'
import { diaryAnswering, openDiary } from './SC11-test-kit'

const MARK = `Mark as no show ${REFERENCE}`
const REASON_BOX = 'Why did the booking not go out?'

/** The diary with Thandi's booking due out today. */
const DUE_TODAY: RouteHandler = diaryAnswering([{ date: TEST_TODAY, collections: [DUE_OUT], returns: [] }])

/** The same diary once the server has the booking down as a no show. */
const MISSED_TODAY: RouteHandler = diaryAnswering([
  { date: TEST_TODAY, collections: [{ ...DUE_OUT, status: 'NO_SHOW', canMarkNoShow: false }], returns: [] },
])

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

async function openTheQuestion(routes: Record<string, RouteHandler>) {
  const opened = await openDiary({ [DIARY_ROUTE]: DUE_TODAY, ...routes })
  await opened.user.click(await screen.findByRole('button', { name: MARK }, SCREEN_WAIT))
  return opened
}

describe('the question', () => {
  it('asks for the reason and says in words what the answer does', async () => {
    await openTheQuestion({})

    expect(screen.getByLabelText(REASON_BOX)).toHaveFocus()
    expect(
      screen.getByText(
        `Marking ${REFERENCE} as a no show means its 2 units go back on the shelf for someone else, and a strike is recorded against ${THANDI.displayName}. Three strikes in twelve months put the account on hold.`,
      ),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: 'Yes, mark as no show' })).toHaveAccessibleDescription(
      /a strike is recorded against/,
    )
  })

  it('sends nothing without a reason, and says so under the box', async () => {
    const { user, network } = await openTheQuestion({ [noShowRoute()]: () => jsonResponse(MARKED_NO_SHOW) })

    await user.click(screen.getByRole('button', { name: 'Yes, mark as no show' }))

    expect(screen.getByText(/Say why in a few words/)).toBeVisible()
    expect(screen.getByLabelText(REASON_BOX)).toHaveFocus()
    expect(network.requestsTo(noShowRoute())).toHaveLength(0)
  })

  it('puts the question away on "Keep the booking", and focus goes back to the button', async () => {
    const { user, network } = await openTheQuestion({})

    await user.click(screen.getByRole('button', { name: 'Keep the booking' }))

    expect(screen.queryByLabelText(REASON_BOX)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: MARK })).toHaveFocus()
    expect(network.requestsTo(noShowRoute())).toHaveLength(0)
  })
})

describe('when the server agrees', () => {
  it('sends the reason once, shows the answer, and reads the diary again', async () => {
    const { user, network } = await openTheQuestion({ [noShowRoute()]: () => jsonResponse(MARKED_NO_SHOW) })
    await user.type(screen.getByLabelText(REASON_BOX), '  Did not arrive by closing  ')
    network.setRoute(DIARY_ROUTE, MISSED_TODAY)

    await user.click(screen.getByRole('button', { name: 'Yes, mark as no show' }))

    const answer = await screen.findByText(`${REFERENCE} is now`, { exact: false }, SCREEN_WAIT)
    expect(answer.closest('[role="status"]')).toHaveFocus()
    expect(within(answer.closest('[role="status"]') as HTMLElement).getByText('No show')).toBeVisible()
    expect(screen.getByText(`The units are back on the shelf and the strike is recorded against ${THANDI.displayName}.`)).toBeVisible()
    expect(network.requestsTo(noShowRoute())).toHaveLength(1)
    expect(network.requestsTo(noShowRoute())[0].body).toEqual({ reason: 'Did not arrive by closing' })
    await waitFor(() => expect(network.requestsTo(DIARY_ROUTE)).toHaveLength(2))
    expect(screen.queryByRole('button', { name: MARK })).not.toBeInTheDocument()
  })
})

describe('when the server refuses', () => {
  it('shows the server sentence for a 409 and reads the diary again', async () => {
    const detail = 'TSH-R-26-000124 was collected at 08:10, so it cannot be a no show.'
    const { user, network } = await openTheQuestion({
      [noShowRoute()]: () => problemResponse(409, { slug: 'illegal-transition', detail }),
    })
    await user.type(screen.getByLabelText(REASON_BOX), 'Did not arrive')

    await user.click(screen.getByRole('button', { name: 'Yes, mark as no show' }))

    const refusal = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(refusal).toHaveTextContent(`${REFERENCE} cannot be marked as a no show`)
    expect(refusal).toHaveTextContent(detail)
    await waitFor(() => expect(network.requestsTo(DIARY_ROUTE)).toHaveLength(2))
  })

  it('puts the message about a refused reason under the box', async () => {
    const { user } = await openTheQuestion({
      [noShowRoute()]: () =>
        problemResponse(422, { errors: { fields: { 'body.reason': 'The reason is at most 200 characters.' } } }),
    })
    await user.type(screen.getByLabelText(REASON_BOX), 'Did not arrive')

    await user.click(screen.getByRole('button', { name: 'Yes, mark as no show' }))

    expect(await screen.findByText('The reason is at most 200 characters.', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByLabelText(REASON_BOX)).toHaveAccessibleDescription(/at most 200 characters\./)
  })
})
