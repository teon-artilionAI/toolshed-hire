/**
 * The photographs of damage reports as tiles, each of which opens one
 * (#83, #112).
 *
 * A tile is a button and never a picture. Pressing it asks the API for a five
 * minute link and sends the window to it, and the bucket serves the photograph
 * as a download. So the page draws nothing from the bucket, and the content
 * security policy, which allows images only from this origin and from data
 * addresses, stays as it is.
 *
 * Each tile is numbered within its report and names the report, so a screen
 * reader hears which photograph it opens. What the last press did is said in
 * a polite status under the tiles, and a refusal in an alert.
 */

import { useRef, useState } from 'react'
import { ImageDown } from 'lucide-react'
import { isApiError } from './api-problem'
import type { DamagePhoto, PhotoLink } from './api/contract'
import { logEvent } from './api/log'
import { ErrorState } from './async-states'
import { fileSize } from './format'
import { photoNavigation } from './photo-navigation'
import { branchDateTime } from './today'
import { Notice } from './ui'

/** A photograph and the words that name it. */
interface NamedPhoto {
  photo: DamagePhoto
  /** Its place in its report, counted from one. */
  count: number
  /** For example "photograph 2 of TSH-D-26-00012", to sit inside a sentence. */
  name: string
}

type Opening =
  | { kind: 'idle' }
  | { kind: 'opening'; name: string }
  | { kind: 'opened'; name: string }
  | { kind: 'failed'; name: string; error: unknown }

/** Number each photograph within its report, oldest first, as the server lists them. */
function namePhotos(photos: readonly DamagePhoto[]): NamedPhoto[] {
  const counts = new Map<string, number>()
  return photos.map((photo) => {
    const count = (counts.get(photo.damageReportId) ?? 0) + 1
    counts.set(photo.damageReportId, count)
    return { photo, count, name: `photograph ${count} of ${photo.damageReportReference}` }
  })
}

/** A name that starts a sentence. */
function capitalised(name: string): string {
  return `${name.charAt(0).toUpperCase()}${name.slice(1)}`
}

function statusWords(opening: Opening): string {
  if (opening.kind === 'opening') return `Opening ${opening.name}.`
  if (opening.kind === 'opened') return `${capitalised(opening.name)} opened as a download.`
  return ''
}

function Refused({ opening }: { opening: Extract<Opening, { kind: 'failed' }> }) {
  const { error, name } = opening
  if (isApiError(error) && error.problem !== null) {
    return (
      <Notice tone="error" title={`${capitalised(name)} did not open`}>
        <p>{error.problem.detail}</p>
      </Notice>
    )
  }
  return <ErrorState heading={`We could not open ${name}`} error={error} />
}

export function PhotoTiles({
  photos,
  label,
  openLink,
}: {
  photos: readonly DamagePhoto[]
  /** What the list is called, for example "Photographs of TSH-D-26-00012". */
  label: string
  /** Asks the API for the link to one photograph. */
  openLink: (photo: DamagePhoto) => Promise<PhotoLink>
}) {
  const [opening, setOpening] = useState<Opening>({ kind: 'idle' })
  // One press at a time. A flag rather than a disabled button, so focus stays
  // on the tile that was pressed.
  const inFlight = useRef(false)
  const named = namePhotos(photos)
  const reportCount = new Set(photos.map((photo) => photo.damageReportId)).size

  async function open({ photo, name }: NamedPhoto): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setOpening({ kind: 'opening', name })
    try {
      const link = await openLink(photo)
      photoNavigation.open(link.url)
      setOpening({ kind: 'opened', name })
    } catch (error) {
      logEvent('warn', 'file.photo_refused', { photo: photo.id, report: photo.damageReportReference })
      setOpening({ kind: 'failed', name, error })
    } finally {
      inFlight.current = false
    }
  }

  return (
    <div className="min-w-0">
      <ul aria-label={label} className="grid gap-sm sm:grid-cols-2 lg:grid-cols-3">
        {named.map((each) => (
          <li key={each.photo.id} className="min-w-0">
            <button
              type="button"
              onClick={() => void open(each)}
              className="flex min-h-11 w-full min-w-0 items-start gap-sm rounded border border-line bg-surface p-sm text-left transition-colors hover:bg-muted"
            >
              <ImageDown className="mt-0.5 h-5 w-5 shrink-0 text-slate-soft" aria-hidden="true" />
              <span className="min-w-0">
                <span className="block wrap-break-word text-sm font-medium text-ink">
                  Photograph {each.count}{' '}
                  {/* The report is said aloud always, and shown when the tiles span more than one. */}
                  <span className={reportCount > 1 ? '' : 'sr-only'}>of {each.photo.damageReportReference}</span>
                </span>{' '}
                <span className="tabular block text-xs text-slate-soft">
                  Added {branchDateTime(each.photo.uploadedAt)}, {fileSize(each.photo.sizeBytes)}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      <p className="field-help">Each photograph opens as a download.</p>
      <p role="status" className="text-sm text-ink">
        {statusWords(opening)}
      </p>
      {opening.kind === 'failed' && (
        <div className="mt-sm">
          <Refused opening={opening} />
        </div>
      )}
    </div>
  )
}
