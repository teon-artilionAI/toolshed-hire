/**
 * The photograph lists of damage reports, as cached queries, and what an
 * upload tells the cache (#83, #112).
 *
 * The photographs of a report start with the damage segment and the
 * photographs of the customer's own hire with the account segment.
 * query-client.ts treats both as never fresh, so a cached list is always asked
 * for again when a screen uses it. The links that open a photograph are not
 * cached at all, because each lasts five minutes and is asked for at the
 * moment a person opens it.
 */

import { queryOptions } from '@tanstack/react-query'
import type { QueryClient, UseQueryResult } from '@tanstack/react-query'
import type { DamagePhoto, DamagePhotoList } from './contract'
import { isPhotosSwitchedOff, listMyHirePhotos, listReportPhotos } from './damage-photos'
import { ACCOUNT_KEY, DAMAGE_KEY } from './query-client'
import { queryPhase } from './query-phase'

const PHOTOS_SEGMENT = 'photos'
const HIRE_PHOTOS_SEGMENT = 'damage-photos'

export const damagePhotoQueries = {
  /** The photographs of one report, by its key, oldest first. */
  ofReport: (reportId: string) =>
    queryOptions({
      queryKey: [DAMAGE_KEY, PHOTOS_SEGMENT, reportId],
      queryFn: ({ signal }) => listReportPhotos(reportId, signal),
    }),

  /** The photographs of every report on the signed in customer's own hire. */
  ofMyHire: (rentalId: string) =>
    queryOptions({
      queryKey: [ACCOUNT_KEY, HIRE_PHOTOS_SEGMENT, rentalId],
      queryFn: ({ signal }) => listMyHirePhotos(rentalId, signal),
    }),
}

/**
 * Mark the list of the report a photograph was added to as out of date, so
 * the screen reads it again and shows the photograph where the server puts it.
 */
export function rememberDamagePhoto(client: QueryClient, photo: DamagePhoto): void {
  void client.invalidateQueries({ queryKey: damagePhotoQueries.ofReport(photo.damageReportId).queryKey })
}

/** Mark the list of one report as out of date. A refusal that says the report
 *  is full calls this, because the list on the screen is behind the server. */
export function forgetReportPhotos(client: QueryClient, reportId: string): void {
  void client.invalidateQueries({ queryKey: damagePhotoQueries.ofReport(reportId).queryKey })
}

/** What a screen needs to know about a list to decide what else to offer. */
export interface PhotoListState {
  /** True while photographs are switched off in this deployment. */
  switchedOff: boolean
  /** How many photographs the list holds, or null until it has loaded. */
  count: number | null
}

/** Read the state of a list the way damage-photo-list.tsx shows it. */
export function photoListState(photos: UseQueryResult<DamagePhotoList>): PhotoListState {
  const phase = queryPhase(photos)
  return {
    switchedOff: phase === 'failed' && isPhotosSwitchedOff(photos.error),
    count: phase === 'ready' && photos.data !== undefined ? photos.data.items.length : null,
  }
}
