/**
 * Every numbered screen and the privacy notice laid out at 360, 768 and 1440
 * pixels wide, and the screens that used to need sideways scrolling looked at
 * closely on a phone.
 *
 * Each screen is opened from the one list in screens.ts, as the role it
 * belongs to, with the API answered by the spec itself, so a layout check
 * never depends on what a database happens to hold and runs with or without a
 * backend. The answers carry long names, addresses and large figures, which
 * are what break a layout. At every width the page may not be wider than the
 * window, and the page heading has to be on the screen. At 360 pixels no box
 * inside the screen may need scrolling sideways either, because a customer
 * reads these on a phone and an assistant may hold one at the counter.
 *
 * My Hires and My Account used to need scrolling sideways at 360 pixels. The
 * list of bookings was a table of six columns inside a box that scrolled, and
 * the account pushed the whole page wider than the window, so both are looked
 * at closely here. So are the catalogue and the asset register with their
 * questions and forms open, and the return and the checkout as the owner sees
 * them with the owner's question open, from owner-answers.ts. The forms and
 * questions of SC-23 are measured in user-management.spec.ts with the same
 * rule from overflow.ts.
 *
 * Each test sets its own viewport, so both browser projects check the same
 * widths.
 */

import { expect, test } from '@playwright/test'
import { ADMIN_SCREENS, ASSET_REGISTER_HEADING, CATALOGUE_HEADING, openAdminScreen } from './admin-answers.ts'
import { openCounterScreen } from './counter-answers.ts'
import { PROFILE, RESERVATIONS, customerScreen, openCustomerScreen } from './customer-answers.ts'
import { LAYOUT_WIDTHS, NARROW_PHONE, ROUNDING_PIXELS, SIDEWAYS_OVERFLOW, pageOverflow } from './overflow.ts'
import { OWNER_COUNTER_SCREENS } from './owner-answers.ts'
import { ALL_SCREENS } from './screens.ts'

for (const viewport of LAYOUT_WIDTHS) {
  test.describe(`at ${viewport.width} pixels`, () => {
    test.use({ viewport })

    for (const visit of ALL_SCREENS) {
      test(`${visit.label} fits ${viewport.width} pixels with its heading on the screen`, async ({ page }) => {
        await visit.open(page)

        await expect(page.getByRole('heading', { level: 1 })).toBeInViewport()
        expect(await pageOverflow(page, viewport.width)).toBeLessThanOrEqual(ROUNDING_PIXELS)
        if (viewport.width === NARROW_PHONE.width) {
          expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
        }
      })
    }
  })
}

test.describe('on a phone 360 pixels wide', () => {
  test.use({ viewport: NARROW_PHONE })

  test('My Hires shows every booking in full, with nothing to scroll sideways', async ({ page }) => {
    await openCustomerScreen(page, customerScreen('SC-07'))

    // Every value of the first booking is on the screen, with its name beside it.
    const first = page.getByRole('row').filter({ hasText: 'TSH-R-26-000124' })
    await first.scrollIntoViewIfNeeded()
    await expect(first.getByText('Hire dates')).toBeVisible()
    await expect(first.getByText('Confirmed')).toBeInViewport()
    await expect(first.getByText(/R\s115\s980[,.]00/)).toBeInViewport()
    await expect(first.getByRole('link', { name: 'View booking TSH-R-26-000124' })).toBeVisible()
    await expect(page.getByRole('row')).toHaveCount(RESERVATIONS.items.length)

    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })

  test('My Account fits with long details, reading and editing', async ({ page }) => {
    await openCustomerScreen(page, customerScreen('SC-09'))
    await expect(page.getByText('Your email address has not been confirmed')).toBeVisible()
    await expect(page.getByRole('article', { name: 'TSH-H-26-000099' })).toBeVisible()

    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)

    await page.getByRole('button', { name: 'Edit my details' }).click()
    await expect(page.getByLabel('Billing address, first line')).toHaveValue(PROFILE.billingAddressLine1)

    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })

  test('the catalogue fits 360 pixels with its questions and the category form open, with nothing to scroll sideways', async ({
    page,
  }) => {
    const formOpen = ADMIN_SCREENS.find((screen) => screen.heading === CATALOGUE_HEADING && screen.path.includes('model='))
    if (formOpen === undefined) throw new Error('ADMIN_SCREENS has no catalogue with its form open.')
    await openAdminScreen(page, formOpen)

    const form = page.getByRole('form', { name: /^The details of / })
    await form.getByLabel('Daily rate, in rand').fill('1300')
    await form.getByRole('button', { name: 'Save the changes' }).click()
    await expect(page.getByRole('heading', { level: 3, name: /^Save the changes to .+\?$/ })).toBeVisible()
    await page.getByRole('button', { name: /^Hide / }).first().click()
    await expect(page.getByRole('heading', { level: 3, name: /^Hide .+ from customers\?$/ })).toBeVisible()
    await page.getByRole('region', { name: 'Categories' }).getByRole('button', { name: 'Add a category' }).click()
    await page.getByRole('button', { name: /^Switch off / }).first().click()
    await expect(page.getByRole('heading', { level: 3, name: /^Switch .+ off\?$/ })).toBeVisible()

    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })

  test('the asset register fits 360 pixels with a unit, its question, its form and the registration open, with nothing to scroll sideways', async ({
    page,
  }) => {
    const unitOpen = ADMIN_SCREENS.find((screen) => screen.heading === ASSET_REGISTER_HEADING && screen.path.includes('asset='))
    if (unitOpen === undefined) throw new Error('ADMIN_SCREENS has no asset register with a unit open.')
    await openAdminScreen(page, unitOpen)

    await page.getByRole('region', { name: 'Move it through its life' }).getByRole('button', { name: 'Retire it' }).click()
    await expect(page.getByRole('heading', { level: 4, name: /^Retire .+\?$/ })).toBeVisible()
    await page.getByRole('button', { name: 'Change the serial number, grade, meter reading or notes' }).click()
    await expect(page.getByRole('form', { name: /^The details of / })).toBeVisible()
    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)

    await page.getByRole('button', { name: 'Register a unit' }).first().click()
    const form = page.getByRole('form', { name: 'The new unit' })
    await form.getByRole('button', { name: 'Register the unit' }).click()
    await expect(page.getByText(/Nothing has been saved yet\. 3 answers need fixing\./)).toBeVisible()
    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })

  for (const owner of OWNER_COUNTER_SCREENS) {
    test(`${owner.name} fits 360 pixels, question and all, with nothing to scroll sideways`, async ({ page }) => {
      await openCounterScreen(page, owner.screen, owner.instead)
      expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)

      await owner.ask(page)
      expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
    })
  }
})
