/**
 * Automated accessibility checks for the public screens.
 *
 * I run axe against each screen with the WCAG 2.2 level AA rule set and fail
 * on anything it rates serious or critical. An automated scan only finds the
 * failures a machine can see, such as contrast, missing names and broken
 * structure. It does not replace using the screens with a keyboard and a
 * screen reader.
 */

import { AxeBuilder } from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { CATALOGUE_HOME, SEARCH, SIGN_IN } from './routes.ts'

/** WCAG 2.2 AA includes every A and AA criterion from 2.0 and 2.1, and axe
 *  tags each version separately, so I ask for all of them. */
const WCAG_22_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

/** The impact levels that fail the run. */
const BLOCKING_IMPACTS = ['serious', 'critical']

for (const route of [CATALOGUE_HOME, SEARCH, SIGN_IN]) {
  test(`${route.path} has no serious or critical accessibility violations`, async ({ page }) => {
    await page.goto(route.path)
    await expect(page.getByRole('heading', { level: 1, name: route.heading })).toBeVisible()

    const results = await new AxeBuilder({ page }).withTags(WCAG_22_AA_TAGS).analyze()

    // I reduce each violation to the rule, its impact and the elements it
    // names, so a failure prints something a person can act on.
    const blocking = results.violations
      .filter((violation) => BLOCKING_IMPACTS.includes(violation.impact ?? ''))
      .map((violation) => ({
        rule: violation.id,
        impact: violation.impact,
        help: violation.help,
        elements: violation.nodes.map((node) => node.target.join(' ')),
      }))

    expect(blocking).toEqual([])
  })
}
