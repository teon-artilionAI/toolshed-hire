/**
 * Damage photographs for the tests of SC-16 and SC-09 (#83, #112), shaped the
 * way the contract for photographs describes them.
 *
 * The photographs belong to the reports in damage-samples.ts. A photograph is
 * only ever described here, never sent, because the screens never draw one.
 * They open it through a signed link, and the link here is on the storage
 * host the server uses, with a query string as long as a real one.
 */

import type { DamagePhoto, DamagePhotoList, DamageReport, PhotoLink, Rental } from '../shared/api/contract'
import { jsonResponse, problemResponse } from './api-mock'
import type { RouteTable } from './api-mock'
import { EARLIER_REPORT, FILED_OFF_HIRE, FILED_ON_THE_HIRE, RESOLVED_REPORT } from './damage-samples'
import { CUSTOMER_HIRE } from './rental-samples'

/** The sentence and the type the server sends while photographs are off. */
export const SWITCHED_OFF_DETAIL = 'Photographs are not switched on yet.'
const SWITCHED_OFF_SLUG = 'feature-switched-off'

export function photosRoute(reportId: string): string {
  return `GET /api/damage-reports/${reportId}/photos`
}

/** Where an upload goes. Uploads are answered by upload-mock.ts, not by this path. */
export function uploadPath(reportId: string): string {
  return `/api/damage-reports/${reportId}/photos`
}

export function photoLinkRoute(reportId: string, photoId: string): string {
  return `GET /api/damage-reports/${reportId}/photos/${photoId}`
}

export function myHirePhotosRoute(rentalId: string): string {
  return `GET /api/me/rentals/${rentalId}/damage-photos`
}

export function myHirePhotoLinkRoute(rentalId: string, photoId: string): string {
  return `GET /api/me/rentals/${rentalId}/damage-photos/${photoId}`
}

/** The photographs of a report, numbered from one, oldest first. */
export function photosOf(report: DamageReport, count: number): DamagePhoto[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `e5500000-0000-4000-8000-${report.id.slice(-6)}${String(index + 1).padStart(6, '0')}`,
    damageReportId: report.id,
    damageReportReference: report.reference,
    contentType: index % 2 === 0 ? 'image/jpeg' : 'image/png',
    sizeBytes: 1_258_291 + index * 1024,
    uploadedAt: `2026-03-12T10:2${index}:00+02:00`,
  }))
}

/** A list, the way both list routes answer. */
export function photoList(items: DamagePhoto[]): DamagePhotoList {
  return { items }
}

/** The two photographs of the open report most tests list. */
export const EARLIER_PHOTOS = photosOf(EARLIER_REPORT, 2)

/** The photograph the upload answers with, the third on the open report. */
export const ADDED_PHOTO: DamagePhoto = photosOf(EARLIER_REPORT, 3)[2]

/** The customer's hire that came back damaged, as the customer is sent it.
 *  Its first unit had its damage reported, and its id is the hire the filed
 *  report belongs to. */
export const DAMAGED_CUSTOMER_HIRE: Rental = {
  ...CUSTOMER_HIRE,
  items: CUSTOMER_HIRE.items.map((item, index) => (index === 0 ? { ...item, damageAssessment: 'DONE' } : item)),
}

/** A hire with no damage reported, beside it on the same page. */
export const UNDAMAGED_CUSTOMER_HIRE: Rental = {
  ...CUSTOMER_HIRE,
  id: '9c3b1f2a-0000-4000-8000-000000000098',
  reference: 'TSH-H-26-000098',
}

/** A second report on the damaged hire, about its other unit. */
const SECOND_REPORT_ON_THE_HIRE: DamageReport = {
  ...FILED_ON_THE_HIRE,
  id: 'd4400000-0000-4000-8000-000000000033',
  reference: 'TSH-D-26-00033',
}

/** The photographs of both reports on the damaged hire, oldest first. */
export const HIRE_PHOTOS: DamagePhoto[] = [...photosOf(FILED_ON_THE_HIRE, 2), ...photosOf(SECOND_REPORT_ON_THE_HIRE, 1)]

/** A signed link, the way the link routes answer. */
export const SIGNED_LINK: PhotoLink = {
  url: 'https://storage.googleapis.com/toolshed-damage-photos/reports/e55/photo.jpg?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Expires=300&X-Goog-Signature=0f3a',
  expiresAt: '2026-03-12T10:25:00+02:00',
}

/** The 503 every photograph route answers while photographs are off. */
export function switchedOff(): Response {
  return problemResponse(503, { slug: SWITCHED_OFF_SLUG, detail: SWITCHED_OFF_DETAIL })
}

/** Routes in which every report in the samples has no photographs, so a test
 *  about something else is not disturbed by the lists. */
export function noPhotos(): RouteTable {
  const reports = [EARLIER_REPORT, RESOLVED_REPORT, FILED_ON_THE_HIRE, FILED_OFF_HIRE]
  return Object.fromEntries(reports.map((report) => [photosRoute(report.id), () => jsonResponse(photoList([]))]))
}
