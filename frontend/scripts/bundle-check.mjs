/**
 * Fails the build when the bundle holds an inline script or evaluates code.
 *
 * The content security policy in vercel.json allows scripts only from this
 * origin, with no 'unsafe-inline' and no 'unsafe-eval', and it requires
 * Trusted Types for every script sink (control C-09). A browser would refuse an
 * inline script or a call to eval at run time, so the visitor would see a
 * broken screen. This catches the same thing when the bundle is built, before
 * anything is deployed.
 *
 * What fails:
 *   a <script> element without a src attribute in any built HTML file
 *   eval( or new Function( anywhere in a built JavaScript file
 *
 * `npm run build` runs it after `vite build`, so the pipeline and every
 * Vercel build run it too. `node scripts/bundle-check.mjs --self-test` proves
 * each pattern still catches what it is meant to.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

/** The build output. */
const DIST_ROOT = fileURLToPath(new URL('../dist', import.meta.url))

/** A script element with no src attribute, so its code is inline. */
const INLINE_SCRIPT = /<script(?![^>]*\bsrc\s*=)[^>]*>/gi

/** A call that turns a string into code. */
const CODE_EVALUATION = /(?<![\w$.])(?:eval\s*\(|new\s+Function\s*\()/g

/**
 * @param {string} directory
 * @returns {string[]} Every file under the directory.
 */
function filesUnder(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    return entry.isDirectory() ? filesUnder(path) : [path]
  })
}

/**
 * @param {string} path
 * @param {string} text
 * @returns {string[]} What in the file the policy would refuse.
 */
function problemsIn(path, text) {
  if (path.endsWith('.html')) {
    return [...text.matchAll(INLINE_SCRIPT)].map((match) => `inline script ${match[0]}`)
  }
  if (path.endsWith('.js')) {
    return [...text.matchAll(CODE_EVALUATION)].map((match) => `code evaluation ${match[0]}`)
  }
  return []
}

function selfTest() {
  /** @type {{ path: string, text: string, expected: number }[]} */
  const cases = [
    { path: 'page.html', text: '<script>alert(1)</script>', expected: 1 },
    { path: 'page.html', text: '<script type="module" crossorigin src="/assets/index.js"></script>', expected: 0 },
    { path: 'code.js', text: 'const run = eval("1 + 1")', expected: 1 },
    { path: 'code.js', text: 'const make = new Function("return 1")', expected: 1 },
    { path: 'code.js', text: 'const value = medieval(1); obj.eval(2)', expected: 0 },
  ]
  for (const { path, text, expected } of cases) {
    const found = problemsIn(path, text).length
    if (found !== expected) {
      console.error(`The bundle check is wrong about ${path} "${text}": found ${found}, expected ${expected}.`)
      process.exit(1)
    }
  }
  console.log('The bundle check catches inline scripts and code evaluation, and passes the rest.')
}

if (process.argv.includes('--self-test')) {
  selfTest()
} else {
  const problems = filesUnder(DIST_ROOT).flatMap((path) =>
    problemsIn(path, readFileSync(path, 'utf8')).map((problem) => `${relative(DIST_ROOT, path)}: ${problem}`),
  )
  if (problems.length > 0) {
    console.error(
      'The bundle holds code the content security policy would refuse at run time. Move the code ' +
        'into a module loaded by src, or remove the evaluation.\n' +
        problems.map((line) => `  ${line}`).join('\n'),
    )
    process.exit(1)
  }
  console.log('The bundle holds no inline script and no code evaluation.')
}
