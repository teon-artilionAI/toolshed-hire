/**
 * The photographs of damage reports in a real browser, under the real content
 * security policy, with the API answered by the spec itself (#83, #112).
 *
 * An assistant on SC-16 chooses a PNG, sees its preview, uploads it while the
 * progress shows, sees it listed and opens it. The owner follows a unit's open
 * damage reports from SC-21 to the damage screen and sees the photographs
 * beside the form that resolves a report. The customer opens the photographs
 * of their own damaged hire on SC-09. Each photograph opens through a signed
 * link on Cloud Storage, answered here as the download the bucket sends, so
 * nothing leaves the machine. While photographs are switched off, SC-16 and
 * SC-09 say so in plain words.
 *
 * Every state is scanned with axe and measured for sideways scrolling, in both
 * browser projects, so the phone width is measured too.
 */

import { expect, test } from '@playwright/test'
import type { Page, Request } from '@playwright/test'
import { ADMIN_SCREENS, openAdminScreen } from './admin-answers.ts'
import type { AdminScreen } from './admin-answers.ts'
import { fulfil } from './answered.ts'
import { ASSET_TAG } from './asset-answers.ts'
import { reportedViolations } from './axe.ts'
import { COUNTER_SCREENS, openCounterScreen } from './counter-answers.ts'
import type { CounterScreen } from './counter-answers.ts'
import { customerScreen, openCustomerScreen } from './customer-answers.ts'
import {
  CLOSED_REPORT_ID,
  DAMAGE_ANSWERS,
  OPEN_REPORT_ID,
  OPEN_REPORT_PHOTOS,
  OPEN_REPORT_REFERENCE,
  photosRoute,
} from './damage-answers.ts'
import { ROUNDING_PIXELS, sidewaysOverflow } from './overflow.ts'
import {
  ONE_PIXEL_PNG,
  STORAGE_ORIGIN,
  SWITCHED_OFF,
  SWITCHED_OFF_SENTENCE,
  damagedHire,
  kept,
  photo,
  photoList,
  signedLink,
} from './photo-answers.ts'
import { MY_RENTALS } from './return-answers.ts'

/** The damage screen from the counter's list of screens. */
function damageScreen(): CounterScreen {
  const found = COUNTER_SCREENS.find((screen) => screen.id === 'SC-16')
  if (found === undefined) throw new Error('COUNTER_SCREENS has no damage screen to open.')
  return found
}

/** One unit of the register open, from the owner's list of screens. */
function unitScreen(): AdminScreen {
  const found = ADMIN_SCREENS.find((screen) => screen.path.includes('?asset='))
  if (found === undefined) throw new Error('ADMIN_SCREENS has no unit of the register to open.')
  return found
}

const CONTROL = `Add a photograph to ${OPEN_REPORT_REFERENCE}`

/** The token the counter answers sign the assistant in with. */
const COUNTER_TOKEN = 'counter-scan-token'

/** The customer's hire with damage reported on its first unit, and the
 *  photographs of the two reports on it. */
const HIRE = damagedHire(MY_RENTALS.items[0])
const HIRE_REPORT_ID = 'd4400000-0000-4000-8000-000000000031'
const HIRE_PHOTOS = [
  photo(HIRE_REPORT_ID, 'TSH-D-26-00031', 1),
  photo(HIRE_REPORT_ID, 'TSH-D-26-00031', 2),
  photo('d4400000-0000-4000-8000-000000000033', 'TSH-D-26-00033', 1),
]
const HIRE_PHOTOS_ROUTE = `GET /api/me/rentals/${HIRE.id}/damage-photos`
const HIRE_BUTTON = `Damage photographs of ${HIRE.reference}`

/** Scan the page, and measure that nothing runs past its box sideways. */
async function expectCleanAndFitting(page: Page, what: string): Promise<void> {
  expect(await reportedViolations(page, what)).toEqual([])
  expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(ROUNDING_PIXELS)
}

/** Answer every signed link the way the bucket does, as a file to save. */
async function answerTheBucket(page: Page): Promise<void> {
  await page.route(`${STORAGE_ORIGIN}/**`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'image/jpeg',
      headers: { 'Content-Disposition': 'attachment; filename="photograph.jpg"' },
      body: ONE_PIXEL_PNG,
    }),
  )
}

/** Press a tile, and return the address the browser saved the photograph from. */
async function openAndSave(page: Page, tile: ReturnType<Page['getByRole']>): Promise<string> {
  const download = page.waitForEvent('download')
  await tile.click()
  return (await download).url()
}

test.describe('the damage screen', () => {
  test('an assistant uploads a PNG, sees it listed and opens it', async ({ page }) => {
    let listed = [...OPEN_REPORT_PHOTOS]
    const added = photo(OPEN_REPORT_ID, OPEN_REPORT_REFERENCE, 3)
    let answerTheUpload: () => void = () => undefined
    const held = new Promise<void>((resolve) => {
      answerTheUpload = resolve
    })
    const uploads: Request[] = []
    await openCounterScreen(page, damageScreen(), {
      [photosRoute(OPEN_REPORT_ID)]: () => photoList(listed),
      [`GET /api/damage-reports/${OPEN_REPORT_ID}/photos/${added.id}`]: signedLink(added.id),
    })
    // A route added later is asked first, so the upload is answered here.
    await page.route(`**/api/damage-reports/${OPEN_REPORT_ID}/photos`, async (route) => {
      if (route.request().method() !== 'POST') return route.fallback()
      uploads.push(route.request())
      await held
      listed = [...listed, added]
      await fulfil(route, kept(added))
    })
    await answerTheBucket(page)
    const entry = page.getByRole('article', { name: OPEN_REPORT_REFERENCE })
    await expect(entry.getByRole('list', { name: `Photographs of ${OPEN_REPORT_REFERENCE}` })).toBeVisible()

    await entry.getByLabel(CONTROL).setInputFiles({ name: 'cracked-bracket.png', mimeType: 'image/png', buffer: ONE_PIXEL_PNG })
    const preview = entry.getByRole('img', { name: 'Preview of cracked-bracket.png' })
    await expect(preview).toBeVisible()
    expect(await preview.getAttribute('src')).toMatch(/^data:image\/png;base64,/)
    // The policy allows images from data addresses, so the preview really drew.
    await expect
      .poll(() => page.evaluate<number>(`document.querySelector('img[alt="Preview of cracked-bracket.png"]').naturalWidth`))
      .toBe(1)
    await expectCleanAndFitting(page, 'SC-16 with a photograph chosen')

    await entry.getByRole('button', { name: `Upload the photograph to ${OPEN_REPORT_REFERENCE}` }).click()
    await expect(entry.getByRole('progressbar', { name: `Uploading the photograph to ${OPEN_REPORT_REFERENCE}` })).toBeVisible()
    answerTheUpload()

    await expect(entry.getByText(`The photograph is added to ${OPEN_REPORT_REFERENCE}.`)).toBeVisible()
    const tile = entry.getByRole('button', { name: new RegExp(`^Photograph 3 of ${OPEN_REPORT_REFERENCE}`) })
    await expect(tile).toBeVisible()
    expect(uploads).toHaveLength(1)
    expect(uploads[0].headers()['content-type']).toBe('image/png')
    expect(uploads[0].headers().authorization).toBe(`Bearer ${COUNTER_TOKEN}`)
    expect(uploads[0].postDataBuffer()?.equals(ONE_PIXEL_PNG)).toBe(true)
    await expectCleanAndFitting(page, 'SC-16 with the photographs listed')

    expect(await openAndSave(page, tile)).toBe(signedLink(added.id).url)
    await expect(entry.getByText(`Photograph 3 of ${OPEN_REPORT_REFERENCE} opened as a download.`)).toBeVisible()
    await expect(page.getByRole('heading', { level: 1, name: 'Record damage' })).toBeVisible()
  })

  test('an upload refused for another branch says why under the control', async ({ page }) => {
    const detail = 'TSH-PC-0007 is held at Cape Town CBD, so only that branch can add photographs to its reports.'
    await openCounterScreen(page, damageScreen())
    await page.route(`**/api/damage-reports/${OPEN_REPORT_ID}/photos`, async (route) => {
      if (route.request().method() !== 'POST') return route.fallback()
      await route.fulfill({
        status: 403,
        contentType: 'application/problem+json',
        body: JSON.stringify({ type: 'https://toolshedhire.co.za/problems/branch-scope', title: 'Forbidden', status: 403, detail }),
      })
    })
    const entry = page.getByRole('article', { name: OPEN_REPORT_REFERENCE })

    await entry.getByLabel(CONTROL).setInputFiles({ name: 'cracked-bracket.png', mimeType: 'image/png', buffer: ONE_PIXEL_PNG })
    await entry.getByRole('button', { name: `Upload the photograph to ${OPEN_REPORT_REFERENCE}` }).click()

    await expect(entry.getByRole('alert')).toHaveText(detail)
    await expectCleanAndFitting(page, 'SC-16 with an upload refused')
  })

  test('says photographs are switched off, and offers no control', async ({ page }) => {
    await openCounterScreen(page, damageScreen(), {
      [photosRoute(OPEN_REPORT_ID)]: SWITCHED_OFF,
      [photosRoute(CLOSED_REPORT_ID)]: SWITCHED_OFF,
    })
    const entry = page.getByRole('article', { name: OPEN_REPORT_REFERENCE })

    await expect(entry.getByText(SWITCHED_OFF_SENTENCE)).toBeVisible()
    await expect(entry.getByLabel(CONTROL)).toHaveCount(0)
    await expectCleanAndFitting(page, 'SC-16 with photographs switched off')
  })
})

test('the owner follows a unit from SC-21 and sees the photographs while resolving its report', async ({ page }) => {
  await openAdminScreen(page, unitScreen(), {
    ...DAMAGE_ANSWERS,
    'GET /api/assets/locator': {
      items: [{ assetTag: ASSET_TAG, modelName: 'Scaffold Tower Aluminium Mobile Five Metre', modelSlug: 'scaffold-tower', categoryName: 'Access and Scaffolding', branchCode: 'CBD', branchName: 'Cape Town CBD', status: 'QUARANTINED', conditionGrade: 'C', dueBackOn: null, rentalReference: null }],
      page: 1,
      pageSize: 50,
      total: 1,
    },
  })

  await page.getByRole('link', { name: /open damage reports, resolve on the damage screen/ }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Record damage' })).toBeVisible()
  const entry = page.getByRole('article', { name: OPEN_REPORT_REFERENCE })
  await expect(entry.getByRole('list', { name: `Photographs of ${OPEN_REPORT_REFERENCE}` })).toBeVisible()
  await entry.getByRole('button', { name: `Resolve ${OPEN_REPORT_REFERENCE}` }).click()

  await expect(entry.getByRole('form', { name: `Resolve ${OPEN_REPORT_REFERENCE}` })).toBeVisible()
  await expect(entry.getByRole('button', { name: /^Photograph \d of/ })).toHaveCount(OPEN_REPORT_PHOTOS.length)
  await expectCleanAndFitting(page, 'SC-16 as the owner resolving a report with its photographs')
})

test.describe('the customer on SC-09', () => {
  test('opens the photographs of their damaged hire and saves one', async ({ page }) => {
    const chosen = HIRE_PHOTOS[2]
    await openCustomerScreen(page, customerScreen('SC-09'), {
      'GET /api/me/rentals': { ...MY_RENTALS, items: [HIRE] },
      [HIRE_PHOTOS_ROUTE]: photoList(HIRE_PHOTOS),
      [`GET /api/me/rentals/${HIRE.id}/damage-photos/${chosen.id}`]: signedLink(chosen.id),
    })
    await answerTheBucket(page)
    const hire = page.getByRole('article', { name: HIRE.reference })

    await hire.getByRole('button', { name: HIRE_BUTTON }).click()

    const list = hire.getByRole('list', { name: `Damage photographs of ${HIRE.reference}` })
    await expect(list.getByRole('button')).toHaveCount(HIRE_PHOTOS.length)
    await expectCleanAndFitting(page, 'SC-09 with the damage photographs listed')
    const tile = list.getByRole('button', { name: /^Photograph 1 of TSH-D-26-00033/ })
    expect(await openAndSave(page, tile)).toBe(signedLink(chosen.id).url)
  })

  test('is told in plain words when photographs are switched off', async ({ page }) => {
    await openCustomerScreen(page, customerScreen('SC-09'), {
      'GET /api/me/rentals': { ...MY_RENTALS, items: [HIRE] },
      [HIRE_PHOTOS_ROUTE]: SWITCHED_OFF,
    })
    const hire = page.getByRole('article', { name: HIRE.reference })

    await hire.getByRole('button', { name: HIRE_BUTTON }).click()

    await expect(hire.getByText(SWITCHED_OFF_SENTENCE)).toBeVisible()
    await expectCleanAndFitting(page, 'SC-09 with photographs switched off')
  })
})
