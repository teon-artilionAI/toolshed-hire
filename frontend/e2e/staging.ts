/**
 * What the journeys tagged `@staging` call to know where they run.
 *
 * The same journeys run on two kinds of project. On the local browser
 * projects they run against the backend on this machine, skip themselves when
 * it is not there, and fall back to the development seed's password. On the
 * staging project they run against the deployed site, never skip, and have no
 * fallback, so a missing password stops the run with its name instead of
 * signing in with the wrong one. The names are in staging-run.ts.
 */

import { test } from '@playwright/test'
import { STAGING_PROJECT } from './staging-run.ts'

/** Whether the test that is running is on the staging project. */
export function onStaging(): boolean {
  return test.info().project.name === STAGING_PROJECT
}

/**
 * A password from the environment.
 *
 * @param variable The variable it is read from.
 * @param developmentFallback What the development seed gives every account,
 *   used on a local project when the variable is not set.
 * @throws Error on the staging project when the variable is not set. The
 *   message names the variable and never a value.
 */
export function passwordFrom(variable: string, developmentFallback: string): string {
  const value = process.env[variable]
  if (value !== undefined && value !== '') return value
  if (onStaging()) {
    throw new Error(
      `${variable} is not set. The staging project signs in with the real staging password and has no ` +
        `fallback, so set ${variable} in the environment of the run.`,
    )
  }
  return developmentFallback
}

/** Say something in the output of the run, and on the test in the report. */
export function note(message: string): void {
  test.info().annotations.push({ type: 'note', description: message })
  process.stdout.write(`${message}\n`)
}
