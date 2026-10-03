/**
 * Tests for reading the name of a file out of `Content-Disposition`.
 *
 * The name a person finds in their downloads is the one the server chose, so
 * both forms of the header are read, and a name that would be a path is not.
 */

import { describe, expect, it } from 'vitest'
import { fileNameFromDisposition } from './content-disposition'

const REPORT_FILE = 'toolshed-gross-contribution-model-2026-09-01-2026-10-01.csv'

describe('the name of a file', () => {
  it.each([
    ['quoted', `attachment; filename="${REPORT_FILE}"`],
    ['bare', `attachment; filename=${REPORT_FILE}`],
    ['with spaces around the sign', `attachment;filename = "${REPORT_FILE}"`],
    ['percent encoded', `attachment; filename*=UTF-8''${REPORT_FILE}`],
  ])('is read when it is %s', (_form, header) => {
    expect(fileNameFromDisposition(header)).toBe(REPORT_FILE)
  })

  it('prefers the percent encoded name when both are sent', () => {
    expect(fileNameFromDisposition(`attachment; filename="plain.csv"; filename*=UTF-8''r%C3%A9sum%C3%A9.csv`)).toBe(
      'résumé.csv',
    )
  })

  it('falls back to the plain name when the encoded one cannot be read', () => {
    expect(fileNameFromDisposition(`attachment; filename*=UTF-8''bad%E0%A4%A.csv; filename="plain.csv"`)).toBe(
      'plain.csv',
    )
  })

  it('unescapes a quoted name', () => {
    expect(fileNameFromDisposition('attachment; filename="a \\"quoted\\" name.csv"')).toBe('a "quoted" name.csv')
  })

  it.each([
    ['no header', null],
    ['no name', 'attachment'],
    ['an empty name', 'attachment; filename=""'],
    ['a path', 'attachment; filename="../../evil.csv"'],
    ['a Windows path', 'attachment; filename="C:\\\\temp\\\\evil.csv"'],
    ['a folder', 'attachment; filename=".."'],
  ])('is null for %s', (_what, header) => {
    expect(fileNameFromDisposition(header)).toBeNull()
  })
})
