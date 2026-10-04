/**
 * Every numbered screen and the privacy notice, each with the way to open it
 * loaded, for the specs that visit all of them.
 *
 * The accessibility spec scans each of these and the narrow screen spec lays
 * each one out at three widths. Both read this one list, so a screen added to
 * the product is added here once and is then scanned and measured. The
 * customer's screens are answered from customer-answers.ts, the counter's from
 * counter-answers.ts and the owner's from admin-answers.ts, so nothing here
 * depends on what a database holds and it all runs with or without a backend.
 *
 * Some screens are visited more than once, with a different view open, such
 * as the report by model and by unit. Each visit carries the identifier of
 * its screen.
 */

import type { Page } from '@playwright/test'
import { ADMIN_SCREENS, openAdminScreen } from './admin-answers.ts'
import { COUNTER_SCREENS, openCounterScreen } from './counter-answers.ts'
import { CUSTOMER_SCREENS, openCustomerScreen } from './customer-answers.ts'

/** One visit to one screen. */
export interface ScreenVisit {
  /** The identifier in navigation.ts, such as SC-07. */
  id: string
  /** The identifier and the address, which tells the visits of one screen apart. */
  label: string
  /** Open it as the role it belongs to, and wait until it has its data. */
  open: (page: Page) => Promise<void>
}

/** How many numbered screens the inventory holds. */
const NUMBERED_SCREEN_COUNT = 24

/** SC-01 to SC-24, the numbered screens of navigation.ts, and the privacy notice. */
export const EXPECTED_SCREEN_IDS: readonly string[] = [
  ...Array.from({ length: NUMBERED_SCREEN_COUNT }, (_, index) => `SC-${String(index + 1).padStart(2, '0')}`),
  'INFO-01',
]

/** Every visit, in the order of the identifiers. */
export const ALL_SCREENS: readonly ScreenVisit[] = [
  ...CUSTOMER_SCREENS.map((screen) => ({
    id: screen.id,
    label: `${screen.id} ${screen.path}`,
    open: (page: Page) => openCustomerScreen(page, screen),
  })),
  ...COUNTER_SCREENS.map((screen) => ({
    id: screen.id,
    label: `${screen.id} ${screen.path}`,
    open: (page: Page) => openCounterScreen(page, screen),
  })),
  ...ADMIN_SCREENS.map((screen) => ({
    id: screen.id,
    label: `${screen.id} ${screen.path}`,
    open: (page: Page) => openAdminScreen(page, screen),
  })),
].sort((first, second) => first.id.localeCompare(second.id))

/** The identifiers no visit covers, which should be none. */
export function screensNotVisited(): string[] {
  const visited = new Set(ALL_SCREENS.map((visit) => visit.id))
  return EXPECTED_SCREEN_IDS.filter((id) => !visited.has(id))
}
