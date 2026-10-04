/**
 * How the narrow screen checks measure a page that runs past the edge of a
 * phone, shared by narrow-screens.spec.ts and user-management.spec.ts.
 *
 * Only a real browser can measure a layout, so the measure is written as text
 * the browser runs. This folder is compiled without the browser types.
 */

import type { Page } from '@playwright/test'

/** The narrowest phone the screens are built for. */
export const NARROW_PHONE = { width: 360, height: 780 }

/**
 * How far anything runs past its box sideways, in pixels. The page itself,
 * and every box inside the screen that is allowed to scroll sideways.
 */
export const SIDEWAYS_OVERFLOW = `Math.max(
  document.documentElement.scrollWidth - document.documentElement.clientWidth,
  ...Array.from(document.querySelectorAll('main *'), (element) =>
    ['auto', 'scroll'].includes(getComputedStyle(element).overflowX)
      ? element.scrollWidth - element.clientWidth
      : 0,
  ),
)`

/** A pixel of rounding is not a scroll bar. */
export const ROUNDING_PIXELS = 1

/** How far the page in front of the browser runs past its box sideways. */
export function sidewaysOverflow(page: Page): Promise<number> {
  return page.evaluate<number>(SIDEWAYS_OVERFLOW)
}
