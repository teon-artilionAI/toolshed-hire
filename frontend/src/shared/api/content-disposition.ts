/**
 * The name the server gives a file it sends.
 *
 * A route that sends a file names it in the `Content-Disposition` header, for
 * example `attachment; filename="toolshed-gross-contribution-model-2026-09-01-2026-10-01.csv"`.
 * The browser saves the file under that name, so the name a person finds in
 * their downloads is the one the server chose and not one made up here.
 *
 * Two forms are read. `filename*=UTF-8''...` carries a name that is percent
 * encoded and wins when both are there, because that is what RFC 6266 says.
 * `filename="..."` or `filename=...` is the plain form. Anything that is not a
 * name a file can have, such as a path, is refused, so a header can never put
 * a file somewhere other than the downloads folder.
 */

import { logEvent } from './log'

/** The header a route names its file in. */
export const CONTENT_DISPOSITION_HEADER = 'Content-Disposition'

/** The percent encoded form, with its character set and an optional language. */
const EXTENDED_NAME = /filename\*\s*=\s*([\w!#$&+.^`|~-]+)'[^']*'([^;]+)/i

/** The plain form, quoted or not. */
const PLAIN_NAME = /filename\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^;\s]+))/i

/** A quoted name escapes a quote or a backslash with a backslash. */
const QUOTED_ESCAPE = /\\(.)/g

/** Separators that would make the name a path. */
const PATH_SEPARATOR = /[/\\]/

/** Below this code a character is a control character, which no file name holds. */
const FIRST_PRINTABLE_CODE = 0x20

/** The names that mean a folder and not a file. */
const FOLDER_NAMES: readonly string[] = ['.', '..']

function decodeExtended(charset: string, encoded: string): string | null {
  if (charset.toLowerCase() !== 'utf-8') {
    logEvent('warn', 'api.file_name_unreadable', { reason: `the name is in ${charset}, and only UTF-8 is read` })
    return null
  }
  try {
    return decodeURIComponent(encoded.trim())
  } catch (cause) {
    // The plain form may still name the file, and when it does not the caller
    // reports the header as unreadable with the endpoint, so this is a warning.
    logEvent('warn', 'api.file_name_unreadable', {
      reason: cause instanceof Error ? `${cause.name} ${cause.message}` : String(cause),
    })
    return null
  }
}

function usable(name: string | null | undefined): string | null {
  const trimmed = name?.trim() ?? ''
  if (trimmed === '' || FOLDER_NAMES.includes(trimmed) || PATH_SEPARATOR.test(trimmed)) return null
  if ([...trimmed].some((character) => character.charCodeAt(0) < FIRST_PRINTABLE_CODE)) return null
  return trimmed
}

/**
 * Read the file name out of a `Content-Disposition` header.
 *
 * @param header The value of the header, or null when the response had none.
 * @returns The name to save the file under, or null when the header names no
 *   usable file.
 */
export function fileNameFromDisposition(header: string | null): string | null {
  if (header === null) return null
  const extended = EXTENDED_NAME.exec(header)
  if (extended) {
    const name = usable(decodeExtended(extended[1], extended[2]))
    if (name !== null) return name
  }
  const plain = PLAIN_NAME.exec(header)
  if (!plain) return null
  const quoted = plain[1]
  return usable(quoted === undefined ? plain[2] : quoted.replace(QUOTED_ESCAPE, '$1'))
}
