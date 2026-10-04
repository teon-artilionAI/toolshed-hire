/**
 * The owner at the counter, answered by the spec itself.
 *
 * The owner's corrections live on two counter screens. The return screen, SC-15,
 * offers a waiver, a reversal and an adjustment on its charges, and the
 * checkout, SC-14, offers the release of a unit and the search for a
 * replacement. Those only show for a signed in administrator, so the
 * accessibility scan and the narrow screen check open both screens with the
 * owner's session in place of the assistant's, through the answers in
 * counter-answers.ts. The checkout is answered short of a unit, so its
 * shortfall shows as well. Each scan opens the owner's question first, so the
 * question is scanned and measured too.
 */

import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { CHECKOUT, CHECKOUT_ROUTE, COUNTER_SCREENS } from './counter-answers.ts'
import type { CounterScreen } from './counter-answers.ts'

const OWNER = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000005',
  email: 'marius@toolshedhire.co.za',
  fullName: 'Marius Pretorius-Vanderwesthuizen',
  role: 'admin',
  branchCode: null,
  emailVerified: true,
}

const OWNER_SESSION = {
  'POST /api/auth/refresh': { accessToken: 'owner-counter-token', tokenType: 'Bearer', expiresIn: 900, user: OWNER },
}

/** The booking once the owner released one of its two units. */
const SHORT_CHECKOUT = {
  ...CHECKOUT,
  units: CHECKOUT.units.slice(1),
  canCheckOut: false,
  refusal: 'TSH-R-26-000124 is 1 unit short, so it cannot go out until it is reallocated.',
  unitsShort: 1,
}

/** A counter screen as the owner sees it, and the question to open on it. */
export interface OwnerCounterScreen {
  name: string
  screen: CounterScreen
  instead: Record<string, unknown>
  /** Open the owner's question and wait for it. */
  ask: (page: Page) => Promise<void>
}

function counterScreen(heading: string): CounterScreen {
  const found = COUNTER_SCREENS.find((screen) => screen.heading === heading)
  if (found === undefined) throw new Error(`COUNTER_SCREENS has no screen headed ${heading} to open.`)
  return found
}

export const OWNER_COUNTER_SCREENS: readonly OwnerCounterScreen[] = [
  {
    name: 'the return with the owner reversing a charge',
    screen: counterScreen('Return and condition inspection'),
    instead: OWNER_SESSION,
    ask: async (page) => {
      await page.getByRole('button', { name: /^Reverse the late fee/ }).click()
      await expect(page.getByRole('heading', { level: 4, name: /^Reverse the late fee of / })).toBeFocused()
    },
  },
  {
    name: 'the checkout short of a unit with the owner releasing another',
    screen: { ...counterScreen('Checkout and deposit'), loaded: '1 unit is missing from this booking' },
    instead: { ...OWNER_SESSION, [CHECKOUT_ROUTE]: SHORT_CHECKOUT },
    ask: async (page) => {
      await page.getByRole('button', { name: /^Release this unit / }).click()
      await expect(page.getByRole('button', { name: 'Yes, release it' })).toBeVisible()
    },
  },
]
