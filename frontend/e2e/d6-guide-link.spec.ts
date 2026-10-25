/**
 * D6, the staged Help link and the published guide.
 *
 * The staging build sets VITE_USER_GUIDE_URL to the GitHub Pages guide. This
 * journey checks the footer link on a desktop and a phone, focuses it with the
 * keyboard, opens it, reads the guide landing page and checks the PDF
 * destination. It changes nothing.
 */

import { expect, test } from '@playwright/test'
import { note, onStaging } from './staging.ts'

const GUIDE_URL = 'https://teon-artilionai.github.io/toolshed-hire/'
const PDF_PATH = 'INSY7315_Task3_UserGuide.pdf'
const PDF_URL = `${GUIDE_URL}${PDF_PATH}`
const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
] as const

test('the Help link reaches the published guide on desktop and mobile', { tag: '@staging' }, async ({
  page,
  context,
  request,
}) => {
  test.skip(!onStaging(), 'This guide check runs on the staging project only.')

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/')
    const help = page.getByRole('link', { name: 'Help' })
    await expect(help).toBeVisible()
    await expect(help).toHaveAttribute('href', GUIDE_URL)
    await help.scrollIntoViewIfNeeded()
    await help.focus()
    await expect(help).toBeFocused()

    const [guide] = await Promise.all([
      context.waitForEvent('page'),
      page.keyboard.press('Enter'),
    ])
    await guide.waitForLoadState('domcontentloaded')
    await expect(guide).toHaveURL(GUIDE_URL)
    await expect(guide.getByRole('heading', { level: 1, name: 'User guide' })).toBeVisible()
    const pdf = guide.getByRole('link', { name: 'Open the user guide PDF' })
    await expect(pdf).toHaveAttribute('href', PDF_PATH)
    await pdf.scrollIntoViewIfNeeded()
    await pdf.focus()
    await expect(pdf).toBeFocused()
    await guide.close()
  }

  const pdfResponse = await request.get(PDF_URL)
  expect(pdfResponse.ok()).toBe(true)
  expect(pdfResponse.headers()['content-type']).toContain('application/pdf')
  note(`D6 Help link reached ${GUIDE_URL} at desktop and mobile widths, and the PDF answered ${pdfResponse.status()}.`)
})
