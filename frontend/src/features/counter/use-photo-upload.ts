/**
 * The upload of one damage photograph, as one request with its progress (#83).
 *
 * It is sent once for each press of the button, and a second press while it
 * is in flight does nothing. It is never repeated by itself, because an upload
 * that timed out may still have stored the photograph.
 *
 * A photograph the server kept marks the list of its report as out of date, so
 * the list is read again and shows it. A refusal keeps the server's sentence
 * to show under the control. A 409 says the report is full and a 503 says
 * photographs are switched off, and both mean the list on the screen is
 * behind, so it is read again too. Leaving the screen abandons an upload in
 * flight.
 */

import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { isApiError } from '../../shared/api-problem'
import type { DamagePhoto } from '../../shared/api/contract'
import { forgetReportPhotos, rememberDamagePhoto } from '../../shared/api/damage-photo-queries'
import { uploadDamagePhoto } from '../../shared/api/damage-photos'
import { logEvent } from '../../shared/api/log'

const HTTP_CONFLICT = 409
const HTTP_SERVICE_UNAVAILABLE = 503
const WHOLE = 100

export type UploadFailure =
  /** The server refused the photograph and said why. */
  | { kind: 'refused'; detail: string }
  /** The API could not be reached, or something else went wrong. */
  | { kind: 'fault'; error: unknown }

export interface PhotoUpload {
  /** True while the upload is in flight. */
  pending: boolean
  /** How much has been sent, from 0 to 100, or null when nothing is being sent. */
  percent: number | null
  /** Why the last upload did not work, until the next one starts. */
  failure: UploadFailure | null
  /** The photograph the last upload added, until the next one starts. */
  added: DamagePhoto | null
  /**
   * Send the photograph. Nothing happens while another is in flight.
   *
   * @param onAdded Called once the server has kept it.
   */
  send: (file: File, onAdded: () => void) => void
  /** Put the last answer away, when the person chooses another file. */
  clear: () => void
}

function isAbandoned(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError'
}

/**
 * @param reportId The key of the report the photograph is added to.
 * @param reportReference Its reference, for the log.
 */
export function usePhotoUpload(reportId: string, reportReference: string): PhotoUpload {
  const queryClient = useQueryClient()
  const [percent, setPercent] = useState<number | null>(null)
  const [failure, setFailure] = useState<UploadFailure | null>(null)
  const [added, setAdded] = useState<DamagePhoto | null>(null)
  // State lands after the event that set it. This is set in the same tick as
  // the request, so a second press can never start another.
  const inFlight = useRef<AbortController | null>(null)

  useEffect(() => () => inFlight.current?.abort(), [])

  async function send(file: File, onAdded: () => void): Promise<void> {
    if (inFlight.current !== null) return
    const controller = new AbortController()
    inFlight.current = controller
    setPercent(0)
    setFailure(null)
    setAdded(null)
    try {
      const photo = await uploadDamagePhoto(reportId, file, {
        signal: controller.signal,
        onProgress: ({ sentBytes, totalBytes }) =>
          setPercent(totalBytes > 0 ? Math.min(WHOLE, Math.round((sentBytes / totalBytes) * WHOLE)) : 0),
      })
      logEvent('info', 'counter.photo_added', { report: reportReference, photo: photo.id, bytes: photo.sizeBytes })
      rememberDamagePhoto(queryClient, photo)
      setAdded(photo)
      onAdded()
    } catch (cause) {
      if (isAbandoned(cause)) return
      const error = isApiError(cause) ? cause : null
      logEvent('warn', 'counter.photo_refused', { report: reportReference, status: error?.status ?? null, bytes: file.size })
      if (error?.status === HTTP_CONFLICT || error?.status === HTTP_SERVICE_UNAVAILABLE) {
        forgetReportPhotos(queryClient, reportId)
      }
      setFailure(error !== null && error.problem !== null ? { kind: 'refused', detail: error.detail } : { kind: 'fault', error: cause })
    } finally {
      if (inFlight.current === controller) inFlight.current = null
      if (!controller.signal.aborted) setPercent(null)
    }
  }

  return {
    pending: percent !== null,
    percent,
    failure,
    added,
    send: (file, onAdded) => void send(file, onAdded),
    clear: () => {
      setFailure(null)
      setAdded(null)
    },
  }
}
