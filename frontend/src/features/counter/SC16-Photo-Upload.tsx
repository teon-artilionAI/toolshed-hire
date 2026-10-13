/**
 * The control on SC-16 that adds a photograph to a damage report (#83).
 *
 * The assistant chooses one JPEG or PNG, sees a preview of it and its size,
 * and presses Upload. The browser checks the type and the size first and says
 * what is wrong in the server's own words, and the server still has the last
 * word. While the photograph goes up a labelled progress bar says how far it
 * has got. A refusal is shown under the control as the server wrote it, tied
 * to the control and announced, and a photograph that was kept is said in a
 * polite status.
 *
 * The preview is a `data:` address, which the content security policy allows.
 */

import { useEffect, useId, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { AlertCircle, Upload } from 'lucide-react'
import { logEvent } from '../../shared/api/log'
import { ErrorState } from '../../shared/async-states'
import { fileSize } from '../../shared/format'
import { countOf } from './counter-labels'
import { PHOTO_LIMITS, photoProblem, readPreview } from './photo-checks'
import { usePhotoUpload } from './use-photo-upload'

/** The media types the control offers, as the `accept` attribute writes them. */
const ACCEPTED = 'image/jpeg,image/png'

/** The preview of the file it was read from, so a late read for an earlier
 *  file is never shown beside a later one. */
interface Preview {
  file: File
  address: string
}

function usePreview(file: File | null): string | null {
  const [preview, setPreview] = useState<Preview | null>(null)
  useEffect(() => {
    if (file === null) return
    let current = true
    readPreview(file).then(
      (address) => {
        if (current) setPreview({ file, address })
      },
      (cause: unknown) => {
        logEvent('warn', 'counter.photo_preview_failed', { file_name: file.name, reason: String(cause) })
      },
    )
    return () => {
      current = false
    }
  }, [file])
  return preview !== null && preview.file === file ? preview.address : null
}

export function PhotoUpload({
  reportId,
  reference,
  remaining,
}: {
  reportId: string
  reference: string
  /** How many more photographs the report can hold. */
  remaining: number
}) {
  const id = useId()
  const inputId = `${id}-photo`
  const helpId = `${id}-help`
  const errorId = `${id}-error`
  const input = useRef<HTMLInputElement>(null)
  const [chosen, setChosen] = useState<File | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const upload = usePhotoUpload(reportId, reference)
  const preview = usePreview(chosen)

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    upload.clear()
    const found = file === null ? null : photoProblem(file)
    setProblem(found)
    setChosen(found === null ? file : null)
  }

  function send() {
    if (chosen === null) return
    upload.send(chosen, () => {
      setChosen(null)
      if (input.current !== null) {
        input.current.value = ''
        input.current.focus()
      }
    })
  }

  const refusal = problem ?? (upload.failure?.kind === 'refused' ? upload.failure.detail : null)
  const describedBy = refusal === null ? helpId : `${helpId} ${errorId}`
  return (
    <div className="mt-md min-w-0">
      <label htmlFor={inputId} className="field-label">
        Add a photograph{' '}
        <span className="sr-only">to {reference}</span>
      </label>
      <p id={helpId} className="field-help mb-xs mt-0">
        {PHOTO_LIMITS} {countOf(remaining, 'more fits', 'more fit')} on this report.
      </p>
      <input
        ref={input}
        id={inputId}
        type="file"
        accept={ACCEPTED}
        disabled={upload.pending}
        onChange={choose}
        aria-describedby={describedBy}
        aria-invalid={refusal === null ? undefined : true}
        className="block w-full min-w-0 text-sm text-ink file:mr-sm file:min-h-11 file:cursor-pointer file:rounded file:border file:border-line file:bg-surface file:px-md file:text-sm file:font-medium file:text-ink hover:file:bg-muted"
      />
      {refusal !== null && (
        <p id={errorId} role="alert" className="field-error">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{refusal}</span>
        </p>
      )}
      {upload.failure?.kind === 'fault' && (
        <div className="mt-sm">
          <ErrorState heading="We could not upload the photograph" error={upload.failure.error} />
        </div>
      )}
      {chosen !== null && (
        <div className="mt-sm flex flex-wrap items-start gap-md">
          {preview !== null && (
            <img
              src={preview}
              alt={`Preview of ${chosen.name}`}
              className="h-24 w-auto max-w-full rounded border border-line object-contain"
            />
          )}
          <div className="min-w-0">
            <p className="wrap-break-word text-sm text-ink">
              {chosen.name}, {fileSize(chosen.size)}
            </p>
            <button type="button" className="btn-primary mt-xs px-md" disabled={upload.pending} onClick={send}>
              <Upload className="h-4 w-4 shrink-0" aria-hidden="true" />
              {upload.pending ? 'Uploading' : 'Upload the photograph'}
              {' '}
              <span className="sr-only">to {reference}</span>
            </button>
          </div>
        </div>
      )}
      {upload.percent !== null && (
        <div className="mt-sm flex items-center gap-sm">
          <progress
            aria-label={`Uploading the photograph to ${reference}`}
            max={100}
            value={upload.percent}
            className="h-2 min-w-0 flex-1 accent-accent"
          />
          <span className="tabular text-sm text-ink" aria-hidden="true">
            {upload.percent}%
          </span>
        </div>
      )}
      <p role="status" className="mt-xs text-sm text-ink">
        {upload.added === null ? '' : `The photograph is added to ${reference}.`}
      </p>
    </div>
  )
}
