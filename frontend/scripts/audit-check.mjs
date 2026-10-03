/**
 * Runs `npm audit` and fails on any high or critical advisory that is not
 * covered by a reviewed, unexpired exception in audit-exceptions.json.
 *
 * `npm audit --audit-level=high` has no way to accept one advisory and keep
 * blocking the rest. When an advisory has no patched version and the only fix
 * on offer is a major upgrade, the choice would otherwise be between turning
 * the audit off and blocking every merge. An exception here names the
 * advisory, says why it does not reach this system, and carries an expiry
 * date, after which the merge is blocked again until somebody looks at it.
 *
 * Only the advisory itself is listed. A package that is vulnerable only
 * because it depends on that one is covered by the same exception, because
 * npm reports it through the original advisory.
 *
 * `npm run audit:check` runs it, and the pipeline runs that on every pull
 * request.
 */

import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

/** The frontend folder. npm is run from here. */
const FRONTEND_ROOT = fileURLToPath(new URL('..', import.meta.url))

/** The reviewed exceptions, beside package.json. */
const EXCEPTIONS_FILE = new URL('../audit-exceptions.json', import.meta.url)

/** The severities that block a merge. Lower ones are reported only. */
const BLOCKING_SEVERITIES = new Set(['high', 'critical'])

/** Pulls the advisory identifier out of the advisory's address. */
const ADVISORY_ID_PATTERN = /GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}/i

/** npm is a .cmd file on Windows, which needs a shell to start. */
const RUN_THROUGH_SHELL = process.platform === 'win32'

function readExceptions() {
  const parsed = JSON.parse(readFileSync(EXCEPTIONS_FILE, 'utf8'))
  const today = new Date().toISOString().slice(0, 10)
  const live = new Map()
  for (const exception of parsed.exceptions) {
    if (!exception.advisory || !exception.reason || !exception.expires) {
      throw new Error(
        `An exception in audit-exceptions.json is missing its advisory, reason or expiry: ${JSON.stringify(exception)}`,
      )
    }
    if (exception.expires < today) {
      console.error(
        `The exception for ${exception.advisory} (${exception.package}) expired on ${exception.expires}. ` +
          'Review the advisory again and either fix it or renew the exception with a new date.',
      )
      continue
    }
    live.set(exception.advisory.toUpperCase(), exception)
  }
  return live
}

function runAudit() {
  const result = spawnSync('npm', ['audit', '--json'], {
    cwd: FRONTEND_ROOT,
    encoding: 'utf8',
    shell: RUN_THROUGH_SHELL,
  })
  if (!result.stdout) {
    throw new Error(`npm audit printed nothing. Its error output was: ${result.stderr}`)
  }
  return JSON.parse(result.stdout)
}

/** Every advisory npm reported, once each, with the package it was raised on. */
function advisoriesIn(report) {
  const found = new Map()
  for (const [packageName, vulnerability] of Object.entries(report.vulnerabilities ?? {})) {
    for (const cause of vulnerability.via) {
      if (typeof cause === 'string') continue
      const id = (cause.url ?? '').match(ADVISORY_ID_PATTERN)?.[0]?.toUpperCase() ?? String(cause.source)
      found.set(id, { id, packageName, severity: cause.severity, title: cause.title, url: cause.url })
    }
  }
  return [...found.values()]
}

function main() {
  const exceptions = readExceptions()
  const advisories = advisoriesIn(runAudit())
  const blocking = []
  for (const advisory of advisories) {
    if (!BLOCKING_SEVERITIES.has(advisory.severity)) {
      console.log(`Reported, not blocking: ${advisory.severity} ${advisory.id} in ${advisory.packageName}. ${advisory.title}`)
    } else if (exceptions.has(advisory.id)) {
      const exception = exceptions.get(advisory.id)
      console.log(`Accepted until ${exception.expires}: ${advisory.severity} ${advisory.id} in ${advisory.packageName}. ${exception.reason}`)
    } else {
      blocking.push(advisory)
    }
  }
  for (const id of exceptions.keys()) {
    if (!advisories.some((advisory) => advisory.id === id)) {
      console.log(`The exception for ${id} no longer matches any advisory and can be removed.`)
    }
  }
  if (blocking.length > 0) {
    for (const advisory of blocking) {
      console.error(`Blocking: ${advisory.severity} ${advisory.id} in ${advisory.packageName}. ${advisory.title} ${advisory.url ?? ''}`)
    }
    console.error(`${blocking.length} high or critical advisory without a reviewed exception. Fix it, or add a reasoned exception with an expiry date.`)
    process.exit(1)
  }
  console.log(`No unreviewed high or critical advisories among ${advisories.length} reported.`)
}

main()
