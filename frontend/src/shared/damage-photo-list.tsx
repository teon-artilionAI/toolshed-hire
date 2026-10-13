/**
 * A list of damage photographs in each of its states (#83, #112).
 *
 * Loading, failed, switched off, empty and listed. The counter, the owner and
 * the customer read their lists through different routes, so the screen reads
 * the list and hands the answer here. While photographs are switched off in a
 * deployment, every route answers 503 with a sentence that says so, and that
 * sentence is shown as it is, in place of the list and of any way to add one.
 */

import type { UseQueryResult } from '@tanstack/react-query'
import { isApiError } from './api-problem'
import type { DamagePhoto, DamagePhotoList as PhotoListAnswer, PhotoLink } from './api/contract'
import { isPhotosSwitchedOff } from './api/damage-photos'
import { queryPhase } from './api/query-phase'
import { ErrorState, LoadingState } from './async-states'
import { PhotoTiles } from './photo-tiles'

/** Said when the server is switched off and sent no sentence of its own. */
const PHOTOS_SWITCHED_OFF_WORDS = 'Photographs are not switched on yet.'

export function DamagePhotoList({
  photos,
  what,
  empty,
  label,
  openLink,
}: {
  photos: UseQueryResult<PhotoListAnswer>
  /** What is being loaded, after "We could not load", for example "the photographs of TSH-D-26-00012". */
  what: string
  /** Said when there are none. */
  empty: string
  /** What the list of tiles is called. */
  label: string
  openLink: (photo: DamagePhoto) => Promise<PhotoLink>
}) {
  const phase = queryPhase(photos)
  if (phase === 'failed' && isPhotosSwitchedOff(photos.error)) {
    const sentence = isApiError(photos.error) ? photos.error.detail : PHOTOS_SWITCHED_OFF_WORDS
    return <p className="text-sm text-slate-soft">{sentence}</p>
  }
  if (phase === 'failed') {
    return <ErrorState what={what} error={photos.error} onRetry={() => void photos.refetch()} />
  }
  if (photos.data === undefined) {
    return <LoadingState label={`Loading ${what}`} shape="rows" count={1} />
  }
  if (photos.data.items.length === 0) {
    return <p className="text-sm text-slate-soft">{empty}</p>
  }
  return (
    <div aria-busy={photos.isFetching}>
      <PhotoTiles photos={photos.data.items} label={label} openLink={openLink} />
    </div>
  )
}
