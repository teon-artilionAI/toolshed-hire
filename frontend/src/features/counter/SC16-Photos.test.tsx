/**
 * Tests for the photographs of a damage report on SC-16 (#83, #112), with the
 * network replaced at `fetch`.
 *
 * Each report lists its photographs with the loading, failed, switched off,
 * empty and listed states. A photograph is a tile and never a picture, and
 * opening one asks for its link and sends the window there. An open report
 * offers the control that adds one until it holds six, and the owner sees the
 * photographs beside the form that resolves the report. The upload itself is
 * in SC16-Photo-Upload.test.tsx.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DamagePhoto, DamageReport, SessionUser } from '../../shared/api/contract'
import { photoNavigation } from '../../shared/photo-navigation'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import type { RouteHandler } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { EARLIER_REPORT, QUARANTINED_AT_BELLVILLE, RESOLVED_REPORT } from '../../test/damage-samples'
import {
  EARLIER_PHOTOS,
  SIGNED_LINK,
  SWITCHED_OFF_DETAIL,
  photoLinkRoute,
  photoList,
  photosOf,
  photosRoute,
  switchedOff,
} from '../../test/photo-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { ACCESS_TOKEN, ADMIN, COUNTER_STAFF, bearerOf } from '../../test/session-samples'
import { REPORT_FULL } from './photo-checks'
import { openDamage, unitWith } from './SC16-test-kit'

const AT = `/counter/damage/${QUARANTINED_AT_BELLVILLE.assetTag}`
const REFERENCE = EARLIER_REPORT.reference
const CONTROL = `Add a photograph to ${REFERENCE}`

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

/** Open the unit with these reports on it, and the open one's list answering. */
async function openPhotos(
  list: RouteHandler,
  { reports = [EARLIER_REPORT], account = COUNTER_STAFF }: { reports?: DamageReport[]; account?: SessionUser } = {},
  routes: Record<string, RouteHandler> = {},
) {
  const opened = await openDamage(
    unitWith(QUARANTINED_AT_BELLVILLE, reports, { [photosRoute(reports[0].id)]: list, ...routes }),
    AT,
    account,
  )
  const entry = await screen.findByRole('article', { name: reports[0].reference }, SCREEN_WAIT)
  return { ...opened, entry }
}

function listing(photos: DamagePhoto[]): RouteHandler {
  return () => jsonResponse(photoList(photos))
}

describe('the list of photographs', () => {
  it('says the photographs are loading while the list answers', async () => {
    const { entry } = await openPhotos(neverAnswers)

    expect(await within(entry).findByText(`Loading the photographs of ${REFERENCE}`)).toBeInTheDocument()
    expect(within(entry).queryByLabelText(CONTROL)).not.toBeInTheDocument()
  })

  it('says when there are none, and offers the control with the limits in words', async () => {
    const { entry } = await openPhotos(listing([]))

    expect(await within(entry).findByText('No photographs of this damage yet.', {}, SCREEN_WAIT)).toBeVisible()
    const control = within(entry).getByLabelText(CONTROL)
    expect(control).toHaveAttribute('type', 'file')
    expect(control).toHaveAttribute('accept', 'image/jpeg,image/png')
    expect(control).toHaveAccessibleDescription('JPEG or PNG, up to 4 MB, at most 6. 6 more fit on this report.')
  })

  it('lists each as a tile that names the photograph and the report, oldest first, and draws no picture', async () => {
    const { entry } = await openPhotos(listing(EARLIER_PHOTOS))

    const list = await within(entry).findByRole('list', { name: `Photographs of ${REFERENCE}` }, SCREEN_WAIT)
    const tiles = within(list).getAllByRole('button')
    expect(tiles).toHaveLength(2)
    expect(tiles[0]).toHaveAccessibleName(`Photograph 1 of ${REFERENCE} Added 12 Mar 2026 at 10:20, 1.2 MB`)
    expect(tiles[1]).toHaveAccessibleName(/^Photograph 2 of TSH-D-26-00012 Added 12 Mar 2026 at 10:21/)
    expect(within(entry).getByText('Each photograph opens as a download.')).toBeVisible()
    expect(entry.querySelector('img')).toBeNull()
  })

  it('says so with the reference when the list fails, and reads it again on a retry', async () => {
    const { user, network, entry } = await openPhotos(() => problemResponse(500, { requestId: 'req-photos-1' }))

    const alert = await within(entry).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent(`We could not load the photographs of ${REFERENCE}`)
    expect(within(alert).getByText('req-photos-1')).toBeVisible()
    expect(within(entry).queryByLabelText(CONTROL)).not.toBeInTheDocument()

    network.setRoute(photosRoute(EARLIER_REPORT.id), listing(EARLIER_PHOTOS))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await within(entry).findByRole('button', { name: /^Photograph 2 of/ }, SCREEN_WAIT)).toBeVisible()
  })

  it('says photographs are switched off in plain words, and offers no control, when the list answers 503', async () => {
    const { entry } = await openPhotos(switchedOff)

    expect(await within(entry).findByText(SWITCHED_OFF_DETAIL, {}, SCREEN_WAIT)).toBeVisible()
    expect(within(entry).queryByLabelText(CONTROL)).not.toBeInTheDocument()
    expect(within(entry).queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('opening a photograph', () => {
  it('asks for its link with the token and sends the window to it', async () => {
    const open = vi.spyOn(photoNavigation, 'open').mockImplementation(() => undefined)
    const photo = EARLIER_PHOTOS[0]
    const { user, network, entry } = await openPhotos(listing(EARLIER_PHOTOS), {}, {
      [photoLinkRoute(EARLIER_REPORT.id, photo.id)]: () => jsonResponse(SIGNED_LINK),
    })

    await user.click(await within(entry).findByRole('button', { name: /^Photograph 1 of/ }, SCREEN_WAIT))

    await waitFor(() => expect(open).toHaveBeenCalledWith(SIGNED_LINK.url))
    expect(open).toHaveBeenCalledTimes(1)
    const asked = network.requestsTo(photoLinkRoute(EARLIER_REPORT.id, photo.id))
    expect(asked).toHaveLength(1)
    expect(bearerOf(asked[0])).toBe(ACCESS_TOKEN)
    expect(await within(entry).findByText(`Photograph 1 of ${REFERENCE} opened as a download.`)).toBeVisible()
  })

  it('shows the server sentence when the link is refused, and goes nowhere', async () => {
    const open = vi.spyOn(photoNavigation, 'open').mockImplementation(() => undefined)
    const detail = 'There is no such photograph on TSH-D-26-00012.'
    const { user, entry } = await openPhotos(listing(EARLIER_PHOTOS), {}, {
      [photoLinkRoute(EARLIER_REPORT.id, EARLIER_PHOTOS[1].id)]: () => problemResponse(404, { detail }),
    })

    await user.click(await within(entry).findByRole('button', { name: /^Photograph 2 of/ }, SCREEN_WAIT))

    const alert = await within(entry).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent(`Photograph 2 of ${REFERENCE} did not open`)
    expect(alert).toHaveTextContent(detail)
    expect(open).not.toHaveBeenCalled()
  })

  it('never opens a link that is not an https address', async () => {
    const open = vi.spyOn(photoNavigation, 'open').mockImplementation(() => undefined)
    const { user, entry } = await openPhotos(listing(EARLIER_PHOTOS), {}, {
      [photoLinkRoute(EARLIER_REPORT.id, EARLIER_PHOTOS[0].id)]: () =>
        jsonResponse({ ...SIGNED_LINK, url: 'javascript:alert(1)' }),
    })

    await user.click(await within(entry).findByRole('button', { name: /^Photograph 1 of/ }, SCREEN_WAIT))

    const alert = await within(entry).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent(`We could not open photograph 1 of ${REFERENCE}`)
    expect(open).not.toHaveBeenCalled()
  })
})

describe('how many a report holds', () => {
  it('counts what still fits under the control', async () => {
    const { entry } = await openPhotos(listing(photosOf(EARLIER_REPORT, 5)))

    expect(await within(entry).findByLabelText(CONTROL, {}, SCREEN_WAIT)).toHaveAccessibleDescription(
      /1 more fits on this report\.$/,
    )
  })

  it('says the report is full and offers no control once it holds six', async () => {
    const { entry } = await openPhotos(listing(photosOf(EARLIER_REPORT, 6)))

    expect(await within(entry).findByText(REPORT_FULL, {}, SCREEN_WAIT)).toBeVisible()
    expect(within(entry).getAllByRole('button', { name: /^Photograph \d of/ })).toHaveLength(6)
    expect(within(entry).queryByLabelText(CONTROL)).not.toBeInTheDocument()
  })

  it('lists the photographs of a closed report, and takes no more', async () => {
    const { entry } = await openPhotos(listing(photosOf(RESOLVED_REPORT, 1)), { reports: [RESOLVED_REPORT] })

    expect(await within(entry).findByRole('button', { name: /^Photograph 1 of TSH-D-26-00009/ }, SCREEN_WAIT)).toBeVisible()
    expect(within(entry).queryByLabelText(/^Add a photograph/)).not.toBeInTheDocument()
  })
})

describe('the owner resolving a report', () => {
  it('sees its photographs beside the form that records the cost, and may add one', async () => {
    const { user, entry } = await openPhotos(listing(EARLIER_PHOTOS), { account: ADMIN })
    await within(entry).findByRole('list', { name: `Photographs of ${REFERENCE}` }, SCREEN_WAIT)

    await user.click(within(entry).getByRole('button', { name: `Resolve ${REFERENCE}` }))

    expect(within(entry).getByRole('form', { name: `Resolve ${REFERENCE}` })).toBeVisible()
    expect(within(entry).getAllByRole('button', { name: /^Photograph \d of/ })).toHaveLength(2)
    expect(within(entry).getByLabelText(CONTROL)).toBeVisible()
  })
})
