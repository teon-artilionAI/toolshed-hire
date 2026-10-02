/**
 * The accessibility scan every browser test shares.
 *
 * I run axe with the WCAG 2.2 level AA rule set and keep only what it rates
 * serious or critical. An automated scan only finds the failures a machine can
 * see, such as contrast, missing names and broken structure. It does not
 * replace using the screens with a keyboard and a screen reader.
 */

import { AxeBuilder } from '@axe-core/playwright'
import type { Page } from '@playwright/test'

/** WCAG 2.2 AA includes every A and AA criterion from 2.0 and 2.1, and axe
 *  tags each version separately, so I ask for all of them. */
const WCAG_22_AA_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

/** The impact levels that fail the run. */
const BLOCKING_IMPACTS = ['serious', 'critical']

/** One violation, cut down to what a person needs to act on it. */
export interface BlockingViolation {
  rule: string
  impact: string | null | undefined
  help: string
  elements: string[]
}

/**
 * Scan the page as it stands and return the violations that fail the run.
 *
 * @returns An empty list when the page is clean. I reduce each violation to the
 *   rule, its impact and the elements it names, so a failure prints something
 *   a person can act on.
 */
export async function blockingViolations(page: Page): Promise<BlockingViolation[]> {
  const results = await new AxeBuilder({ page }).withTags(WCAG_22_AA_TAGS).analyze()
  return results.violations
    .filter((violation) => BLOCKING_IMPACTS.includes(violation.impact ?? ''))
    .map((violation) => ({
      rule: violation.id,
      impact: violation.impact,
      help: violation.help,
      elements: violation.nodes.map((node) => node.target.join(' ')),
    }))
}
