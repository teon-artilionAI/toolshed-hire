/**
 * The API answered by the spec itself, for the photographs of damage reports
 * (#83, #112).
 *
 * The damage screen lists the photographs of each report, the owner sees them
 * while resolving one, and the customer sees those of their own hire. A
 * photograph opens through a signed link on Cloud Storage, which is answered
 * here too, as a download, so no request leaves the machine. The photograph
 * the journey uploads is a real PNG of one pixel, small enough to write out.
 */

import { Answered, problem } from './answered.ts'
import { dateFromToday } from './hire-dates.ts'

/** A valid PNG of one transparent pixel. */
export const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
)

/** Where every signed link in these answers points. The spec answers it. */
export const STORAGE_ORIGIN = 'https://storage.googleapis.com'

/** The sentence every photograph route answers with while photographs are off. */
export const SWITCHED_OFF_SENTENCE = 'Photographs are not switched on yet.'

/** The 503 every photograph route answers while photographs are off. */
export const SWITCHED_OFF = problem(503, 'feature-switched-off', SWITCHED_OFF_SENTENCE)

/** One photograph of a report, numbered from one within it. */
export function photo(reportId: string, reference: string, number: number) {
  return {
    id: `e5500000-0000-4000-8000-${reportId.slice(-6)}${String(number).padStart(6, '0')}`,
    damageReportId: reportId,
    damageReportReference: reference,
    contentType: 'image/jpeg',
    sizeBytes: 3_801_088 + number,
    uploadedAt: `${dateFromToday(-3)}T11:2${number}:00+02:00`,
  }
}

/** A list, the way both list routes answer. */
export function photoList(items: ReturnType<typeof photo>[]) {
  return { items }
}

/** The signed link of one photograph, the way both link routes answer. */
export function signedLink(photoId: string) {
  return {
    url: `${STORAGE_ORIGIN}/toolshed-damage-photos/${photoId}.jpg?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Expires=300&X-Goog-Signature=5c0ffee`,
    expiresAt: `${dateFromToday(0)}T23:59:00+02:00`,
  }
}

/** What the upload answers once the server has kept the photograph. */
export function kept(added: ReturnType<typeof photo>): Answered {
  return new Answered(201, { ...added, contentType: 'image/png', sizeBytes: ONE_PIXEL_PNG.length })
}

/** The customer's hire whose first unit came back damaged, from a hire the
 *  customer answers already hold. */
export function damagedHire<Hire extends { items: { damageAssessment: string }[] }>(hire: Hire): Hire {
  return { ...hire, items: hire.items.map((item, index) => (index === 0 ? { ...item, damageAssessment: 'DONE' } : item)) }
}
