/**
 * Tests for adding a photograph to a damage report on SC-16 (#83), with the
 * lists answered at `fetch` and the upload answered at `XMLHttpRequest`.
 *
 * The assistant chooses a file, sees a preview, and presses Upload. The bytes
 * go up with the session's token and the file's own media type while a
 * labelled progress bar moves, and the list is read again once the server has
 * kept the photograph. The browser checks the type and the size first, and
 * every refusal the server sends is shown under the control as it was written.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MAX_PHOTO_BYTES } from '../../shared/api/damage-photos'
import { jsonResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { EARLIER_REPORT, QUARANTINED_AT_BELLVILLE } from '../../test/damage-samples'
import { ADDED_PHOTO, EARLIER_PHOTOS, photoList, photosRoute, uploadPath } from '../../test/photo-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { ACCESS_TOKEN } from '../../test/session-samples'
import { heldOpen, keptAnswer, mockUploads, refusedAnswer } from '../../test/upload-mock'
import type { UploadHandler } from '../../test/upload-mock'
import { PHOTO_NOT_SUPPORTED, PHOTO_TOO_LARGE } from './photo-checks'
import { openDamage, unitWith } from './SC16-test-kit'

const AT = `/counter/damage/${QUARANTINED_AT_BELLVILLE.assetTag}`
const REFERENCE = EARLIER_REPORT.reference
const CONTROL = `Add a photograph to ${REFERENCE}`
const UPLOAD = `Upload the photograph to ${REFERENCE}`

/** The first bytes of a PNG and a little more. The browser never decodes it. */
const PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13])

function pngFile(name = 'cracked-plate.png'): File {
  return new File([PNG_BYTES], name, { type: 'image/png' })
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

/** Open the open report with two photographs on it, and uploads answered by `handler`. */
async function openControl(handler?: UploadHandler) {
  const uploads = mockUploads(handler)
  const opened = await openDamage(
    unitWith(QUARANTINED_AT_BELLVILLE, [EARLIER_REPORT], {
      [photosRoute(EARLIER_REPORT.id)]: () => jsonResponse(photoList(EARLIER_PHOTOS)),
    }),
    AT,
  )
  const entry = await screen.findByRole('article', { name: REFERENCE }, SCREEN_WAIT)
  const control = await within(entry).findByLabelText(CONTROL, {}, SCREEN_WAIT)
  // The accept list is the browser's business. These tests choose files it would hide.
  const user = userEvent.setup({ applyAccept: false })
  return { ...opened, user, uploads, entry, control }
}

describe('a photograph the server keeps', () => {
  it('previews it, sends its bytes with the token, shows the progress, and lists it', async () => {
    const held = heldOpen()
    const file = pngFile()
    const { user, network, uploads, entry, control } = await openControl(() =>
      keptAnswer(ADDED_PHOTO, { progress: [file.size / 2], until: held.until }),
    )

    await user.upload(control, file)
    const preview = await within(entry).findByRole('img', { name: 'Preview of cracked-plate.png' })
    expect(preview.getAttribute('src')).toMatch(/^data:image\/png;base64,/)
    expect(within(entry).getByText('cracked-plate.png, 1 KB')).toBeVisible()

    await user.click(within(entry).getByRole('button', { name: UPLOAD }))

    const progress = await within(entry).findByRole('progressbar', { name: `Uploading the photograph to ${REFERENCE}` })
    await waitFor(() => expect(progress).toHaveAttribute('value', '50'))
    expect(within(entry).getByRole('button', { name: `Uploading to ${REFERENCE}` })).toBeDisabled()
    expect(uploads.uploads).toHaveLength(1)
    const [sent] = uploads.uploads
    expect(sent.method).toBe('POST')
    expect(sent.path).toBe(uploadPath(EARLIER_REPORT.id))
    expect(sent.headers.Authorization).toBe(`Bearer ${ACCESS_TOKEN}`)
    expect(sent.headers['Content-Type']).toBe('image/png')
    expect(sent.body).toBe(file)
    expect(sent.timeout).toBeGreaterThan(0)

    network.setRoute(photosRoute(EARLIER_REPORT.id), () => jsonResponse(photoList([...EARLIER_PHOTOS, ADDED_PHOTO])))
    held.release()

    expect(await within(entry).findByText(`The photograph is added to ${REFERENCE}.`, {}, SCREEN_WAIT)).toBeVisible()
    expect(await within(entry).findByRole('button', { name: /^Photograph 3 of/ }, SCREEN_WAIT)).toBeVisible()
    expect(within(entry).queryByRole('progressbar')).not.toBeInTheDocument()
    expect(within(entry).queryByRole('button', { name: UPLOAD })).not.toBeInTheDocument()
    expect(within(entry).getByLabelText(CONTROL)).toHaveAccessibleDescription(/3 more fit on this report\.$/)
    expect(network.requestsTo(photosRoute(EARLIER_REPORT.id)).length).toBeGreaterThanOrEqual(2)
  })
})

describe('a photograph the server refuses', () => {
  it.each([
    [413, 'That photograph is larger than 4 MB. Take it again at a lower resolution, or send a smaller copy.'],
    [415, 'That file is not a JPEG or PNG photograph. Choose a photograph taken with a camera or a phone.'],
    [409, 'This damage report already has 6 photographs, which is as many as a report can hold.'],
    [403, 'TSH-PC-0007 is held at Cape Town CBD, so only that branch can add photographs to its reports.'],
    [422, 'That photograph could not be opened. It may be damaged or only partly sent. Take it again and try once more.'],
  ])('shows a %i under the control, as the server wrote it', async (status, detail) => {
    const { user, uploads, entry, control } = await openControl(() => refusedAnswer(status, detail))

    await user.upload(control, pngFile())
    await user.click(within(entry).getByRole('button', { name: UPLOAD }))

    const alert = await within(entry).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent(detail)
    expect(within(entry).getByLabelText(CONTROL)).toHaveAccessibleDescription(new RegExp(`${detail.replace(/\./g, '\\.')}$`))
    expect(within(entry).getByLabelText(CONTROL)).toHaveAttribute('aria-invalid', 'true')
    expect(uploads.uploads).toHaveLength(1)
    expect(within(entry).queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('reads the list again after a 409, and says the report is full', async () => {
    const detail = 'This damage report already has 6 photographs, which is as many as a report can hold.'
    const { user, network, entry, control } = await openControl(() => refusedAnswer(409, detail, 'photo-limit-reached'))
    network.setRoute(photosRoute(EARLIER_REPORT.id), () =>
      jsonResponse(photoList([...EARLIER_PHOTOS, ...Array.from({ length: 4 }, (_, index) => ({ ...ADDED_PHOTO, id: `${ADDED_PHOTO.id}-${index}` }))])),
    )

    await user.upload(control, pngFile())
    await user.click(within(entry).getByRole('button', { name: UPLOAD }))

    expect(await within(entry).findByText(/^This report holds 6 photographs/, {}, SCREEN_WAIT)).toBeVisible()
    expect(within(entry).queryByLabelText(CONTROL)).not.toBeInTheDocument()
  })

  it('says it could not reach the server when the upload never arrives', async () => {
    const { user, entry, control } = await openControl(() => ({ status: 'network' }))

    await user.upload(control, pngFile())
    await user.click(within(entry).getByRole('button', { name: UPLOAD }))

    expect(await within(entry).findByRole('alert', {}, SCREEN_WAIT)).toHaveTextContent('We could not upload the photograph')
    expect(within(entry).getByRole('button', { name: UPLOAD })).toBeEnabled()
  })
})

describe('the checks in the browser', () => {
  it('refuses a file that is not a JPEG or a PNG, and sends nothing', async () => {
    const { user, uploads, entry, control } = await openControl()

    await user.upload(control, new File(['GIF89a'], 'plate.gif', { type: 'image/gif' }))

    expect(within(entry).getByRole('alert')).toHaveTextContent(PHOTO_NOT_SUPPORTED)
    expect(control).toHaveAccessibleDescription(new RegExp(`${PHOTO_NOT_SUPPORTED.replace(/\./g, '\\.')}$`))
    expect(within(entry).queryByRole('button', { name: UPLOAD })).not.toBeInTheDocument()
    expect(uploads.uploads).toHaveLength(0)
  })

  it('refuses a photograph past 4 MB, and sends nothing', async () => {
    const { user, uploads, entry, control } = await openControl()

    await user.upload(control, new File([new Uint8Array(MAX_PHOTO_BYTES + 1)], 'huge.jpg', { type: 'image/jpeg' }))

    expect(within(entry).getByRole('alert')).toHaveTextContent(PHOTO_TOO_LARGE)
    expect(within(entry).queryByRole('button', { name: UPLOAD })).not.toBeInTheDocument()
    expect(uploads.uploads).toHaveLength(0)
  })

  it('takes the refusal away once a good file is chosen', async () => {
    const { user, entry, control } = await openControl()
    await user.upload(control, new File(['GIF89a'], 'plate.gif', { type: 'image/gif' }))
    expect(within(entry).getByRole('alert')).toBeVisible()

    await user.upload(control, pngFile())

    expect(within(entry).queryByRole('alert')).not.toBeInTheDocument()
    expect(within(entry).getByRole('button', { name: UPLOAD })).toBeEnabled()
    expect(control).not.toHaveAttribute('aria-invalid')
  })
})
