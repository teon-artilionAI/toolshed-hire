/**
 * Fails when a container width is written with a size the spacing scale
 * shadows.
 *
 * Under Tailwind 4 a named spacing step wins over the container size of the
 * same name. The theme in src/index.css names its spacing steps xs to 2xl, so
 * a bare `max-w-sm` compiles to 0.5rem rather than 24rem and squeezes whatever
 * it was meant to hold. Container widths are written `max-w-(--container-sm)`
 * instead, and this finds any bare one before it ships.
 *
 * `npm run lint` runs it after oxlint, and the fast checks run that on every
 * push. `node scripts/container-widths-check.mjs --self-test` proves the
 * pattern still catches what it is meant to.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

/** The source folder that is checked. */
const SOURCE_ROOT = fileURLToPath(new URL('../src', import.meta.url))

/** The spacing steps src/index.css defines, which shadow the container sizes. */
const SHADOWED_SIZES = ['xs', 'sm', 'md', 'lg', 'xl', '2xl']

const BARE_CONTAINER_WIDTH = new RegExp(
  `(?<![\\w-])(?:min|max)-w-(?:${SHADOWED_SIZES.join('|')})(?![\\w-])`,
  'g',
)

/** Files that can carry a class name. */
const SOURCE_FILE = /\.(tsx?|css)$/

/**
 * @param {string} directory
 * @returns {string[]} Every source file under the directory.
 */
function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    return SOURCE_FILE.test(entry.name) ? [path] : []
  })
}

/**
 * @param {string} text
 * @returns {string[]} The bare widths in the text.
 */
function bareWidths(text) {
  return [...text.matchAll(BARE_CONTAINER_WIDTH)].map((match) => match[0])
}

/** A CSS block comment, which may explain the rule without breaking it. */
const CSS_COMMENT = /\/\*[\s\S]*?\*\//g

/**
 * @param {string} path
 * @param {string} text
 * @returns {string} The text, with comments removed from a stylesheet.
 */
function withoutCssComments(path, text) {
  return path.endsWith('.css') ? text.replace(CSS_COMMENT, '') : text
}

function selfTest() {
  const caught = bareWidths('<div className="mx-auto max-w-sm">')
  const passed = bareWidths('<div className="max-w-(--container-sm) p-sm max-w-full">')
  if (caught.join() !== 'max-w-sm' || passed.length !== 0) {
    console.error(`The container width pattern is wrong. Caught ${caught.join()} and passed ${passed.join()}.`)
    process.exit(1)
  }
  console.log('The container width pattern catches a bare width and passes a container token.')
}

if (process.argv.includes('--self-test')) {
  selfTest()
} else {
  const offenders = sourceFiles(SOURCE_ROOT).flatMap((path) =>
    bareWidths(withoutCssComments(path, readFileSync(path, 'utf8'))).map(
      (width) => `${relative(SOURCE_ROOT, path)}: ${width}`,
    ),
  )
  if (offenders.length > 0) {
    console.error(
      'These container widths use a size the spacing scale shadows, so they would compile to a ' +
        'spacing step. Write them as max-w-(--container-<size>) instead.\n' +
        offenders.map((line) => `  ${line}`).join('\n'),
    )
    process.exit(1)
  }
  console.log('No container width uses a size the spacing scale shadows.')
}
