/**
 * The CSV of SC-22, saved by a real browser under the Content Security Policy.
 *
 * The report fetches the CSV with the access token and hands the bytes to the
 * browser through a temporary address and a link pressed once. Only a real
 * browser can show that the file is then saved, under the name the server
 * gave it, with every byte it sent, and that the policy a visitor gets does
 * not stop it. The API is answered by the spec, so this runs with or without
 * a backend. The journey against the real backend is in reporting.spec.ts.
 */

import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { ADMIN_SCREENS, CSV_BODY, CSV_FILE_NAME, answerTheCsv, openAdminScreen } from './admin-answers.ts'

test('the report saves the CSV under the name the server gave it, with the token, byte for byte', async ({ page }) => {
  const [, report] = ADMIN_SCREENS
  const policyViolations: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error' && /Content Security Policy/i.test(message.text())) policyViolations.push(message.text())
  })
  await openAdminScreen(page, report)
  let token: string | null = null
  await page.route('**/api/admin/reports/utilisation.csv?*', async (route) => {
    token = route.request().headers().authorization ?? null
    await answerTheCsv(route)
  })

  const saving = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download CSV' }).click()
  const download = await saving

  expect(download.suggestedFilename()).toBe(CSV_FILE_NAME)
  expect(await readFile(await download.path(), 'utf8')).toBe(CSV_BODY)
  expect(token).toBe('Bearer owner-scan-token')
  await expect(page.getByText(`Downloaded ${CSV_FILE_NAME}.`)).toBeVisible()
  expect(policyViolations).toEqual([])
})
