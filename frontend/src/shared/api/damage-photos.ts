/**
 * The photograph routes of a damage report (#83, #112).
 *
 * Staff at the branch that holds the unit, and the owner, attach a photograph
 * to a report and list and open the photographs of any report. The customer of
 * a hire lists and opens the photographs of every report on that hire, through
 * routes of their own under `/api/me/rentals`.
 *
 * A photograph is never fetched by the browser. Opening one asks the API for a
 * signed link that lasts five minutes, and the bucket serves the link as a
 * download. The content security policy allows images only from this origin
 * and from `data:`, and requests only to this origin, so the bytes could not
 * be shown or fetched here anyway. That is on purpose.
 *
 * Every one of these routes answers 503 while photographs are switched off,
 * with a problem whose type ends in `feature-switched-off`.
 */

import { isApiError, malformedResponse } from '../api-problem'
import { api } from './client'
import type { DamagePhoto, DamagePhotoList, PhotoLink } from './contract'
import { readTimestamp } from './damage-reports'
import { uploadFile } from './photo-upload'
import type { UploadOptions } from './photo-upload'
import { readCount, readList, readObject, readText } from './read'
import { problemTypeEndsWith } from './session-seam'

/** The most a photograph may weigh, 4 MB. The server's limit, checked in the
 *  browser first so a person is told before the upload starts. */
export const MAX_PHOTO_BYTES = 4 * 1024 * 1024

/** The most photographs one report may hold. */
export const MAX_PHOTOS_PER_REPORT = 6

/** The media types the server keeps. It decides by the first bytes, so these
 *  are what the browser checks before it sends anything. */
export const PHOTO_MEDIA_TYPES: readonly string[] = ['image/jpeg', 'image/png']

/** How the `type` of the 503 ends while photographs are switched off. */
const SWITCHED_OFF = 'feature-switched-off'

const HTTP_SERVICE_UNAVAILABLE = 503

/** The only scheme a link to a photograph may have. Anything else is not a
 *  photograph, and is never handed to the browser to open. */
const LINK_PROTOCOL = 'https:'

/** Read one photograph, checking every member the contract names. */
export function readDamagePhoto(value: unknown, path: string): DamagePhoto {
  const record = readObject(value, path, 'a damage photograph')
  return {
    id: readText(record, 'id', path),
    damageReportId: readText(record, 'damageReportId', path),
    damageReportReference: readText(record, 'damageReportReference', path),
    contentType: readText(record, 'contentType', path),
    sizeBytes: readCount(record, 'sizeBytes', path),
    uploadedAt: readTimestamp(record, 'uploadedAt', path),
  }
}

function readDamagePhotoList(value: unknown, path: string): DamagePhotoList {
  const record = readObject(value, path, 'a list of damage photographs')
  return { items: readList(record, 'items', path, readDamagePhoto) }
}

/** Read a link, and refuse one that is not an https address. */
export function readPhotoLink(value: unknown, path: string): PhotoLink {
  const record = readObject(value, path, 'a link to a photograph')
  const url = readText(record, 'url', path)
  if (protocolOf(url) !== LINK_PROTOCOL) {
    throw malformedResponse(path, `Expected field url from ${path} to be an https address.`)
  }
  return { url, expiresAt: readTimestamp(record, 'expiresAt', path) }
}

/** The scheme of an address, or null when it is not an address at all. */
function protocolOf(address: string): string | null {
  try {
    return new URL(address).protocol
  } catch (cause) {
    if (cause instanceof TypeError) return null
    throw cause
  }
}

/** A key from the server or the address is always encoded. */
function photosOfReport(reportId: string): string {
  return `/damage-reports/${encodeURIComponent(reportId)}/photos`
}

function photosOfMyHire(rentalId: string): string {
  return `/me/rentals/${encodeURIComponent(rentalId)}/damage-photos`
}

/** Whether a failure says photographs are switched off in this deployment. */
export function isPhotosSwitchedOff(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_SERVICE_UNAVAILABLE && problemTypeEndsWith(error, SWITCHED_OFF)
}

/**
 * GET /api/damage-reports/{id}/photos. The photographs of one report, oldest
 * first, for staff and the owner.
 *
 * @throws ApiError with status 404 for no such report, and 503 while
 *   photographs are switched off.
 */
export function listReportPhotos(reportId: string, signal?: AbortSignal): Promise<DamagePhotoList> {
  return api.get(photosOfReport(reportId), readDamagePhotoList, { signal })
}

/**
 * GET /api/damage-reports/{id}/photos/{photoId}. A five minute link that opens
 * one photograph of a report as a download.
 *
 * @throws ApiError with status 404 for no such report or photograph, and 503
 *   while photographs are switched off.
 */
export function reportPhotoLink(reportId: string, photoId: string): Promise<PhotoLink> {
  return api.get(`${photosOfReport(reportId)}/${encodeURIComponent(photoId)}`, readPhotoLink)
}

/**
 * GET /api/me/rentals/{id}/damage-photos. The photographs of every damage
 * report on the signed in customer's own hire, oldest first.
 *
 * @throws ApiError with status 404 for a hire that is not theirs, and 503
 *   while photographs are switched off.
 */
export function listMyHirePhotos(rentalId: string, signal?: AbortSignal): Promise<DamagePhotoList> {
  return api.get(photosOfMyHire(rentalId), readDamagePhotoList, { signal })
}

/**
 * GET /api/me/rentals/{id}/damage-photos/{photoId}. A five minute link that
 * opens one photograph of the customer's own hire as a download.
 *
 * @throws ApiError with status 404 for a hire that is not theirs or a
 *   photograph not on it, and 503 while photographs are switched off.
 */
export function myHirePhotoLink(rentalId: string, photoId: string): Promise<PhotoLink> {
  return api.get(`${photosOfMyHire(rentalId)}/${encodeURIComponent(photoId)}`, readPhotoLink)
}

/**
 * POST /api/damage-reports/{id}/photos. Attaches one JPEG or PNG photograph,
 * sent as the bytes of the file with the file's own media type.
 *
 * Sent once for each press of the button and never repeated by itself.
 *
 * @throws ApiError with status 413 past 4 MB, 415 for anything that is not a
 *   JPEG or a PNG, 409 for a seventh photograph, 422 for one that cannot be
 *   opened or has too many pixels, 403 at another branch, 404 for no such
 *   report, 429 while the server is busy with others, and 503 while
 *   photographs are switched off. Each carries a sentence to show as it is.
 */
export function uploadDamagePhoto(reportId: string, file: File, options: UploadOptions = {}): Promise<DamagePhoto> {
  return uploadFile(photosOfReport(reportId), file, file.type, readDamagePhoto, options)
}
