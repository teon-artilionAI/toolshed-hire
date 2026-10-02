/**
 * Generates the wire types from the backend's OpenAPI document, or checks that
 * the committed copy is still what that document produces.
 *
 * `npm run api:types` writes src/shared/api/schema.d.ts. I commit that file, so
 * the type checker has it without a generation step, and a change to the
 * contract shows up in the same diff as the code that follows it.
 *
 * `npm run api:types:check` generates again into a temporary folder and
 * compares the result with the committed file. The pipeline runs it, so a
 * backend change that nobody regenerated the types for fails there and not in
 * front of a customer.
 *
 * Both modes go through `generate`, so the check can never run with different
 * options from the ones the committed file was made with.
 */

import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

/** The frontend folder. Every relative path below is read from here. */
const FRONTEND_ROOT = fileURLToPath(new URL('..', import.meta.url))

/** The document the backend commits. It is the one source of the wire types. */
const OPENAPI_DOCUMENT = '../backend/openapi.json'

/** The generated file, as committed. */
const COMMITTED_SCHEMA = 'src/shared/api/schema.d.ts'

/** The generator's own entry point, run with the Node that is running this. */
const GENERATOR_CLI = join(FRONTEND_ROOT, 'node_modules', 'openapi-typescript', 'bin', 'cli.js')

/**
 * The backend describes a free form object, such as the `errors` member of a
 * problem document, as an object with no listed properties. The generator's
 * default for that is an object that may hold nothing at all, which is wrong.
 * This option makes it an object of unknown values, which is what is sent.
 */
const GENERATOR_OPTIONS = ['--empty-objects-unknown']

/** The argument that turns a run into a comparison. */
const CHECK_FLAG = '--check'

const TEMPORARY_FOLDER_PREFIX = 'toolshed-api-types-'
const TEMPORARY_FILE_NAME = 'schema.d.ts'

const EXIT_FAILURE = 1

/**
 * A failure this script expects and can explain. Its message says what was
 * attempted and what to do about it, so it is printed without a stack.
 */
class ApiTypesFailure extends Error {}

/**
 * Generate the types into one file.
 *
 * @param {string} outputPath Where to write, absolute or relative to the frontend folder.
 * @throws {ApiTypesFailure} When the document is missing or the generator fails.
 */
function generate(outputPath) {
  if (!existsSync(join(FRONTEND_ROOT, OPENAPI_DOCUMENT))) {
    throw new ApiTypesFailure(
      `Tried to generate the wire types from ${OPENAPI_DOCUMENT} and that file is not there. ` +
        'It is committed by the backend, so check out the whole repository.',
    )
  }
  const run = spawnSync(
    process.execPath,
    [GENERATOR_CLI, OPENAPI_DOCUMENT, '--output', outputPath, ...GENERATOR_OPTIONS],
    { cwd: FRONTEND_ROOT, encoding: 'utf8' },
  )
  if (run.error || run.status !== 0) {
    throw new ApiTypesFailure(
      `Tried to generate the wire types from ${OPENAPI_DOCUMENT} into ${outputPath} and the ` +
        `generator did not finish (exit status ${run.status}).\n` +
        `${run.error?.message ?? ''}${run.stdout}${run.stderr}`,
    )
  }
}

/**
 * Read a generated file with its line endings made the same on every machine.
 *
 * Git may check the committed file out with Windows line endings. That is not
 * a difference in the contract, so it must not fail the check.
 *
 * @param {string} path
 * @returns {string[]} The lines of the file.
 */
function readLines(path) {
  return readFileSync(path, 'utf8').replaceAll('\r\n', '\n').split('\n')
}

/**
 * Generate into a temporary folder and compare with the committed file.
 *
 * @throws {ApiTypesFailure} When the committed file is missing or out of date.
 */
function check() {
  const committedPath = join(FRONTEND_ROOT, COMMITTED_SCHEMA)
  if (!existsSync(committedPath)) {
    throw new ApiTypesFailure(
      `Tried to check ${COMMITTED_SCHEMA} against ${OPENAPI_DOCUMENT} and the generated file ` +
        'is not there. Run "npm run api:types" and commit the result.',
    )
  }
  const folder = mkdtempSync(join(tmpdir(), TEMPORARY_FOLDER_PREFIX))
  try {
    const freshPath = join(folder, TEMPORARY_FILE_NAME)
    generate(freshPath)
    const fresh = readLines(freshPath)
    const committed = readLines(committedPath)
    const firstDifference = fresh.findIndex((line, index) => line !== committed[index])
    if (firstDifference !== -1 || fresh.length !== committed.length) {
      const lineNumber = (firstDifference === -1 ? fresh.length : firstDifference) + 1
      throw new ApiTypesFailure(
        `${COMMITTED_SCHEMA} is not what ${OPENAPI_DOCUMENT} generates. The first difference ` +
          `is at line ${lineNumber}. Run "npm run api:types", fix any type error that follows, ` +
          'and commit the result.',
      )
    }
    console.log(`${COMMITTED_SCHEMA} matches ${OPENAPI_DOCUMENT}.`)
  } finally {
    rmSync(folder, { recursive: true, force: true })
  }
}

try {
  if (process.argv.includes(CHECK_FLAG)) {
    check()
  } else {
    generate(COMMITTED_SCHEMA)
    console.log(`Wrote ${COMMITTED_SCHEMA} from ${OPENAPI_DOCUMENT}.`)
  }
} catch (error) {
  // Anything I did not expect keeps its stack, so it can be traced.
  if (!(error instanceof ApiTypesFailure)) throw error
  console.error(error.message)
  process.exitCode = EXIT_FAILURE
}
