/**
 * What the browser checks about a damage photograph before it sends one, and
 * the preview it shows of the file chosen (#83).
 *
 * The server has the last word. It decides the format by the first bytes and
 * refuses with sentences of its own, and the screen shows those as they come.
 * These checks only save a person a wasted upload, so they say the same
 * sentences the server would.
 *
 * The preview is a `data:` address read from the file, because the content
 * security policy allows images from `data:` and not from the `blob:`
 * addresses a quicker preview would need.
 */

import { MAX_PHOTO_BYTES, MAX_PHOTOS_PER_REPORT, PHOTO_MEDIA_TYPES } from '../../shared/api/damage-photos'

const BYTES_PER_MEGABYTE = 1024 * 1024

const MAX_PHOTO_MEGABYTES = MAX_PHOTO_BYTES / BYTES_PER_MEGABYTE

/** The limits, in words, under the control that picks a photograph. */
export const PHOTO_LIMITS = `JPEG or PNG, up to ${MAX_PHOTO_MEGABYTES} MB, at most ${MAX_PHOTOS_PER_REPORT}.`

/** The sentences the server sends for the same faults. */
export const PHOTO_TOO_LARGE =
  `That photograph is larger than ${MAX_PHOTO_MEGABYTES} MB. Take it again at a lower resolution, or send a smaller copy.`
export const PHOTO_NOT_SUPPORTED =
  'That file is not a JPEG or PNG photograph. Choose a photograph taken with a camera or a phone.'
export const PHOTO_EMPTY = 'No photograph arrived. Choose the photograph and try again.'

/** Said in place of the control once a report holds as many as it can. */
export const REPORT_FULL = `This report holds ${MAX_PHOTOS_PER_REPORT} photographs, which is as many as a report can hold.`

/** What is wrong with a file before it is sent, or null when nothing is. */
export function photoProblem(file: File): string | null {
  if (!PHOTO_MEDIA_TYPES.includes(file.type)) return PHOTO_NOT_SUPPORTED
  if (file.size === 0) return PHOTO_EMPTY
  if (file.size > MAX_PHOTO_BYTES) return PHOTO_TOO_LARGE
  return null
}

/**
 * Read a file into a `data:` address for its preview.
 *
 * @throws The error the reader met, when the file cannot be read.
 */
export function readPreview(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result)
      else reject(new TypeError(`The preview of ${file.name} was not read as an address.`))
    }
    reader.onerror = () => reject(reader.error ?? new Error(`The preview of ${file.name} could not be read.`))
    reader.readAsDataURL(file)
  })
}
