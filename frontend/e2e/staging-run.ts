/**
 * The staging project's names, and whether a run asked for it.
 *
 * The staging project runs the journeys tagged `@staging` against the
 * deployed staging site, as the pipeline does after each staging deploy with
 * `npx playwright test --project=staging`. It starts no preview server, and it
 * signs in with the real staging passwords, which it only ever reads from the
 * environment. playwright.config.ts reads this file, so it imports nothing
 * from the test runner. The helpers the journeys call are in staging.ts.
 */

/** The name `--project` selects it by. */
export const STAGING_PROJECT = 'staging'

/** The tag a journey carries to run on staging as well. */
export const STAGING_TAG = '@staging'

/** The address of the staging site, for example https://toolshed-hire-staging.vercel.app. */
export const STAGING_URL_VARIABLE = 'STAGING_URL'

/** The password of the seeded customers. */
export const CUSTOMER_PASSWORD_VARIABLE = 'E2E_CUSTOMER_PASSWORD'

/** The password of the seeded staff and the owner. */
export const STAFF_PASSWORD_VARIABLE = 'E2E_STAFF_PASSWORD'

/** Everything the staging project needs from the environment. */
const STAGING_VARIABLES: readonly string[] = [STAGING_URL_VARIABLE, CUSTOMER_PASSWORD_VARIABLE, STAFF_PASSWORD_VARIABLE]

const PROJECT_FLAG = '--project'

/**
 * The projects a command line asked for, as `--project=name` or
 * `--project name`.
 *
 * @returns An empty list when it named none, which means every project.
 */
export function projectsAskedFor(argv: readonly string[]): string[] {
  const asked: string[] = []
  argv.forEach((argument, index) => {
    if (argument.startsWith(`${PROJECT_FLAG}=`)) asked.push(argument.slice(PROJECT_FLAG.length + 1))
    else if (argument === PROJECT_FLAG && index + 1 < argv.length) asked.push(argv[index + 1])
  })
  return asked
}

/** The names of the variables the staging project needs that are not set.
 *  Only the names, never a value. */
export function missingStagingVariables(environment: Record<string, string | undefined>): string[] {
  return STAGING_VARIABLES.filter((name) => (environment[name] ?? '') === '')
}

/**
 * The staging address, checked.
 *
 * @returns Undefined when the variable is not set, so the project is left out.
 * @throws Error when it is set to something that is not an http or https address.
 */
export function stagingAddress(environment: Record<string, string | undefined>): string | undefined {
  const raw = environment[STAGING_URL_VARIABLE]
  if (raw === undefined || raw === '') return undefined
  let address: URL
  try {
    address = new URL(raw)
  } catch (cause) {
    throw new Error(`${STAGING_URL_VARIABLE} is "${raw}", which is not an address. Set it to the staging site, for example https://toolshed-hire-staging.vercel.app.`, { cause })
  }
  if (address.protocol !== 'https:' && address.protocol !== 'http:') {
    throw new Error(`${STAGING_URL_VARIABLE} is "${raw}", which is not a web address. It has to start with https:// or http://.`)
  }
  return address.origin
}
