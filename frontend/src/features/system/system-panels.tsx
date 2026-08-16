/**
 * The pieces the connectivity panel is assembled from.
 *
 * They live here rather than in shared/ui.tsx because none of them belongs to
 * the product. This is a development screen, and its parts should not become
 * something a product screen imports by accident.
 */

import type { ReactNode } from 'react'
import { FlaskConical } from 'lucide-react'
import { Notice, StatusPill } from '../../shared/ui'
import type { ApiError } from '../../shared/api'

/**
 * Where an asynchronous call has got to.
 *
 * A discriminated union rather than three loose booleans, so a render cannot
 * describe a state that cannot happen, such as loaded and failed at once.
 */
export type Loadable<T> =
  | { state: 'idle' }
  | { state: 'loading' }
  | { state: 'ready'; value: T }
  | { state: 'failed'; error: ApiError }

/** How to start the backend, quoted where a reader needs it rather than
 *  filed in a README they would have to go and find. */
export const START_BACKEND_COMMAND = 'uvicorn app.main:app --reload --port 8000'

/** A yes or no fact about the system, shown as a pill so the answer survives
 *  greyscale printing. `AVAILABLE` and `QUARANTINED` are the existing status
 *  vocabulary, reused rather than a new colour scale invented here. */
export function FactRow({
  label,
  affirmative,
  yes,
  no,
  detail,
}: {
  label: string
  affirmative: boolean
  yes: string
  no: string
  detail?: string
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-sm border-t border-line py-sm first:border-t-0">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{label}</p>
        {detail && <p className="mt-xs break-all font-mono text-xs text-slate-soft">{detail}</p>}
      </div>
      <StatusPill status={affirmative ? 'AVAILABLE' : 'QUARANTINED'} label={affirmative ? yes : no} />
    </div>
  )
}

/** A labelled value, monospaced, for the things a reader needs to compare
 *  character by character such as an origin and a URL. */
export function LiteralRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-t border-line py-sm first:border-t-0">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-soft">{label}</p>
      <p className="mt-xs break-all font-mono text-sm text-ink">{value}</p>
    </div>
  )
}

/**
 * What went wrong, in the words the failure itself supplied.
 *
 * An unreachable backend gets the softer tone and the command, because during
 * document work the API being absent is the normal state rather than a fault,
 * and what the reader needs then is the line to type rather than a stack trace.
 */
export function FailureNotice({ error, what }: { error: ApiError; what: string }) {
  if (error.isBackendUnreachable) {
    return (
      <Notice tone="warn" title="The backend is not running">
        <p>{`${what} did not get through. ${error.detail}`}</p>
        <p className="mt-sm">
          This is the only screen that needs the API. The other twenty four read from fixtures
          and are unaffected. Start it from the backend directory with its virtual environment
          active:
        </p>
        <p className="mt-xs break-all font-mono text-xs">{START_BACKEND_COMMAND}</p>
      </Notice>
    )
  }
  return (
    <Notice tone="error" title={`${error.title}${error.status ? ` (HTTP ${error.status})` : ''}`}>
      <p>{error.detail}</p>
      {error.problem && (
        <p className="mt-sm break-all font-mono text-xs text-slate-soft">
          {error.problem.type}
        </p>
      )}
    </Notice>
  )
}

/** The banner that says, unambiguously, that this screen is not part of the
 *  assessed inventory. It is the first thing on the page for that reason. */
export function DevelopmentScreenBanner({ children }: { children: ReactNode }) {
  return (
    <div className="mb-lg rounded-lg border-2 border-dashed border-slate-faint bg-muted p-md">
      <p className="flex items-center gap-sm font-mono text-xs uppercase tracking-wide text-slate-soft">
        <FlaskConical className="h-4 w-4 shrink-0" aria-hidden="true" />
        Development and demonstration screen
      </p>
      <div className="mt-sm text-sm text-slate-soft">{children}</div>
    </div>
  )
}
