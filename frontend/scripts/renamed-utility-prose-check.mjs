/**
 * Fails when a sentence carries a Tailwind utility where a plain word belongs.
 *
 * The Tailwind 4 upgrade tool renamed bare utilities whose meaning changed,
 * `ring` to `ring-3`, `shadow` to `shadow-sm` and `blur` to `blur-sm`. It
 * also rewrote those words where they stood alone in a string, so "ring your
 * branch" became "ring-3 your branch" on every error screen (#121). A class
 * list follows a utility with another class, and a sentence follows it with
 * an ordinary word, so a renamed utility followed by a word that cannot be a
 * class is a sentence the tool broke.
 *
 * `npm run lint` runs it after oxlint. `node scripts/renamed-utility-prose-check.mjs
 * --self-test` proves the pattern still catches what it is meant to.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

/** The source folder that is checked. */
const SOURCE_ROOT = fileURLToPath(new URL('../src', import.meta.url))

/** The utilities the upgrade renamed to a name that was once an ordinary word. */
const RENAMED = ['ring-3', 'shadow-sm', 'blur-sm']

/** A utility followed by the next token on the same line. */
const RENAMED_THEN_NEXT = new RegExp(`(?<![\\w-])(${RENAMED.join('|')})[ \\t]+([^\\s'"\`]+)`, 'g')

/** Utilities that are a single plain word, so they cannot be told apart by their shape. */
const SINGLE_WORD_UTILITIES = new Set([
  'block', 'border', 'capitalize', 'container', 'contents', 'fixed', 'flex', 'grid', 'grow',
  'hidden', 'inline', 'invisible', 'italic', 'lowercase', 'relative', 'absolute', 'rounded',
  'shadow', 'shrink', 'static', 'sticky', 'transition', 'truncate', 'underline', 'uppercase',
  'visible',
])

/** Files that can carry a class name or a sentence. */
const SOURCE_FILE = /\.tsx?$/

/**
 * @param {string} token
 * @returns {boolean} Whether the token can be a class in a class list.
 */
function looksLikeAClass(token) {
  return /[-:/[\]]/.test(token) || SINGLE_WORD_UTILITIES.has(token)
}

/**
 * @param {string} text
 * @returns {string[]} Each renamed utility that is followed by a word, with that word.
 */
function brokenSentences(text) {
  return [...text.matchAll(RENAMED_THEN_NEXT)]
    .filter((match) => !looksLikeAClass(match[2]))
    .map((match) => `${match[1]} ${match[2]}`)
}

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

function selfTest() {
  /** @type {{ text: string, expected: number }[]} */
  const cases = [
    { text: "'Try again, and ring-3 your branch if it keeps happening.'", expected: 1 },
    { text: '`If you need to change it, ring-3 ${branch}.`', expected: 1 },
    { text: 'className="ring-3 ring-accent focus-visible:outline-hidden"', expected: 0 },
    { text: 'className="shadow-sm rounded border border-line"', expected: 0 },
    { text: "'Ring your branch and we will arrange it.'", expected: 0 },
  ]
  for (const { text, expected } of cases) {
    const found = brokenSentences(text).length
    if (found !== expected) {
      console.error(`The prose check is wrong about ${text}: found ${found}, expected ${expected}.`)
      process.exit(1)
    }
  }
  console.log('The prose check catches a renamed utility in a sentence, and passes a class list.')
}

if (process.argv.includes('--self-test')) {
  selfTest()
} else {
  const problems = sourceFiles(SOURCE_ROOT).flatMap((path) =>
    brokenSentences(readFileSync(path, 'utf8')).map((found) => `${relative(SOURCE_ROOT, path)}: "${found}"`),
  )
  if (problems.length > 0) {
    console.error(
      'These sentences carry a renamed Tailwind utility where a plain word belongs. Put the word back.\n' +
        problems.map((line) => `  ${line}`).join('\n'),
    )
    process.exit(1)
  }
  console.log('No sentence carries a renamed Tailwind utility.')
}
