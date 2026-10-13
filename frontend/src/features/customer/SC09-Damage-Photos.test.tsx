/**
 * Tests for the damage photographs of the customer's own hires on SC-09
 * (#112), with the network replaced at `fetch`.
 *
 * Only a hire whose damage was reported offers them, and the list is read
 * only when the customer opens it, so a page of hires costs no request for
 * photographs until somebody asks. The list has its loading, failed, switched
 * off, empty and listed states, and a photograph opens through the customer's
 * own link route.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PROFILE } from '../../test/account-samples'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import type { RouteHandler } from '../../test/api-mock'
import {
  DAMAGED_CUSTOMER_HIRE,
  HIRE_PHOTOS,
  SIGNED_LINK,
  SWITCHED_OFF_DETAIL,
  UNDAMAGED_CUSTOMER_HIRE,
  myHirePhotoLinkRoute,
  myHirePhotosRoute,
  photoList,
  switchedOff,
} from '../../test/photo-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { MY_RENTALS_ROUTE, rentalPage } from '../../test/rental-samples'
import { ACCESS_TOKEN, bearerOf } from '../../test/session-samples'
import { photoNavigation } from '../../shared/photo-navigation'
import { HISTORY_PAGE_SIZE } from './SC09-Hire-History'
import { openAccount, withProfile } from './SC09-test-kit'

const HIRE = DAMAGED_CUSTOMER_HIRE
const PHOTOS_ROUTE = myHirePhotosRoute(HIRE.id)
const BUTTON = `Damage photographs of ${HIRE.reference}`

/** Open My Account with a damaged hire and an undamaged one, and the list answering. */
async function openHires(list: RouteHandler, routes: Record<string, RouteHandler> = {}) {
  const opened = await openAccount(
    withProfile(PROFILE, {
      [MY_RENTALS_ROUTE]: () =>
        jsonResponse(rentalPage([HIRE, UNDAMAGED_CUSTOMER_HIRE], { pageSize: HISTORY_PAGE_SIZE })),
      [PHOTOS_ROUTE]: list,
      ...routes,
    }),
  )
  const hire = await screen.findByRole('article', { name: HIRE.reference }, SCREEN_WAIT)
  return { ...opened, hire }
}

describe('which hires offer photographs', () => {
  it('offers them only on a hire whose damage was reported, and reads nothing until asked', async () => {
    const { network, hire } = await openHires(() => jsonResponse(photoList(HIRE_PHOTOS)))

    const button = within(hire).getByRole('button', { name: BUTTON })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    const other = screen.getByRole('article', { name: UNDAMAGED_CUSTOMER_HIRE.reference })
    expect(within(other).queryByRole('button', { name: /^Damage photographs/ })).not.toBeInTheDocument()
    expect(network.requests.filter((request) => request.path.endsWith('/damage-photos'))).toHaveLength(0)
  })
})

describe('the list, once opened', () => {
  it('says it is loading while the list answers', async () => {
    const { user, hire } = await openHires(neverAnswers)

    await user.click(within(hire).getByRole('button', { name: BUTTON }))

    expect(within(hire).getByRole('button', { name: BUTTON })).toHaveAttribute('aria-expanded', 'true')
    expect(await within(hire).findByText(`Loading the damage photographs of ${HIRE.reference}`)).toBeInTheDocument()
  })

  it('lists every photograph of the hire with the report it belongs to, asked with the token', async () => {
    const { user, network, hire } = await openHires(() => jsonResponse(photoList(HIRE_PHOTOS)))

    await user.click(within(hire).getByRole('button', { name: BUTTON }))

    const list = await within(hire).findByRole('list', { name: `Damage photographs of ${HIRE.reference}` }, SCREEN_WAIT)
    const tiles = within(list).getAllByRole('button')
    expect(tiles.map((tile) => tile.textContent?.split('Added')[0].trim())).toEqual([
      'Photograph 1 of TSH-D-26-00031',
      'Photograph 2 of TSH-D-26-00031',
      'Photograph 1 of TSH-D-26-00033',
    ])
    expect(bearerOf(network.requestsTo(PHOTOS_ROUTE)[0])).toBe(ACCESS_TOKEN)
    expect(hire.querySelector('img')).toBeNull()
  })

  it('opens a photograph through the link route of the hire', async () => {
    const open = vi.spyOn(photoNavigation, 'open').mockImplementation(() => undefined)
    const photo = HIRE_PHOTOS[2]
    const { user, network, hire } = await openHires(() => jsonResponse(photoList(HIRE_PHOTOS)), {
      [myHirePhotoLinkRoute(HIRE.id, photo.id)]: () => jsonResponse(SIGNED_LINK),
    })
    await user.click(within(hire).getByRole('button', { name: BUTTON }))

    await user.click(await within(hire).findByRole('button', { name: /^Photograph 1 of TSH-D-26-00033/ }, SCREEN_WAIT))

    await waitFor(() => expect(open).toHaveBeenCalledWith(SIGNED_LINK.url))
    expect(network.requestsTo(myHirePhotoLinkRoute(HIRE.id, photo.id))).toHaveLength(1)
  })

  it('says when no photographs were taken', async () => {
    const { user, hire } = await openHires(() => jsonResponse(photoList([])))

    await user.click(within(hire).getByRole('button', { name: BUTTON }))

    expect(await within(hire).findByText('No photographs were taken of the damage on this hire.', {}, SCREEN_WAIT)).toBeVisible()
  })

  it('says photographs are switched off in plain words when the list answers 503', async () => {
    const { user, hire } = await openHires(switchedOff)

    await user.click(within(hire).getByRole('button', { name: BUTTON }))

    expect(await within(hire).findByText(SWITCHED_OFF_DETAIL, {}, SCREEN_WAIT)).toBeVisible()
    expect(within(hire).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says so with the reference when the list fails', async () => {
    const { user, hire } = await openHires(() => problemResponse(500, { requestId: 'req-hire-photos-1' }))

    await user.click(within(hire).getByRole('button', { name: BUTTON }))

    const alert = await within(hire).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent(`We could not load the damage photographs of ${HIRE.reference}`)
    expect(within(alert).getByText('req-hire-photos-1')).toBeVisible()
  })

  it('closes again, and keeps the list hidden', async () => {
    const { user, hire } = await openHires(() => jsonResponse(photoList(HIRE_PHOTOS)))
    await user.click(within(hire).getByRole('button', { name: BUTTON }))
    await within(hire).findByRole('list', { name: `Damage photographs of ${HIRE.reference}` }, SCREEN_WAIT)

    await user.click(within(hire).getByRole('button', { name: BUTTON }))

    expect(within(hire).getByRole('button', { name: BUTTON })).toHaveAttribute('aria-expanded', 'false')
    expect(within(hire).queryByRole('list', { name: `Damage photographs of ${HIRE.reference}` })).not.toBeInTheDocument()
  })
})
