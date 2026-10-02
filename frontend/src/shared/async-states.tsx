/**
 * The two states every screen that reads from the API shares.
 *
 * `LoadingState` is a skeleton. It takes the shape of what is on its way, so
 * the page does not jump when the real content lands, and it tells assistive
 * technology that the region is busy and what it is waiting for.
 *
 * `ErrorState` says what could not be loaded in plain words, offers to try
 * again, and shows the request id small enough to ignore and easy to select.
 * It never shows the raw error, a status code or a stack. The third state, the
 * empty one, is `EmptyState` in ui.tsx.
 */

import type { ReactNode } from 'react'
import { AlertCircle, RotateCw } from 'lucide-react'
import { failureWords } from './failure-words'

/** The shapes a skeleton can stand in for. */
export type SkeletonShape = 'tiles' | 'links' | 'cards' | 'rows' | 'detail'

/** One block per shape, sized like the content it stands in for. */
const BLOCK_CLASS: Record<SkeletonShape, string> = {
  tiles: 'h-28',
  links: 'h-20',
  cards: 'h-72',
  rows: 'h-44',
  detail: 'h-96',
}

/** The grid each shape is laid out on, matching the loaded layout. */
const GRID_CLASS: Record<SkeletonShape, string> = {
  tiles: 'grid gap-md sm:grid-cols-3',
  links: 'grid gap-md sm:grid-cols-2 lg:grid-cols-4',
  cards: 'grid gap-md sm:grid-cols-2 lg:grid-cols-3',
  rows: 'flex flex-col gap-md',
  detail: 'grid gap-lg lg:grid-cols-3',
}

const DEFAULT_SKELETON_COUNT = 3

export function LoadingState({
  label,
  shape = 'rows',
  count = DEFAULT_SKELETON_COUNT,
}: {
  /** What is loading, as a sentence a screen reader announces. Leave it out
   *  only when the screen already has a status line that says the same. */
  label?: string
  shape?: SkeletonShape
  /** How many blocks to draw. */
  count?: number
}) {
  return (
    <div aria-busy="true">
      {label && (
        <p role="status" className="sr-only">
          {label}
        </p>
      )}
      <div className={`animate-pulse ${GRID_CLASS[shape]}`} aria-hidden="true">
        {Array.from({ length: count }, (_, index) => (
          <div
            key={index}
            className={`rounded-lg border border-line bg-surface ${BLOCK_CLASS[shape]} ${
              shape === 'detail' && index === 0 ? 'lg:col-span-2' : ''
            }`}
          >
            <div className="m-md h-4 w-1/2 rounded bg-muted" />
            <div className="mx-md h-4 w-2/3 rounded bg-muted" />
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * What the error state is about. A read names what could not be loaded. An
 * action that failed, such as a sign in, writes the whole heading instead,
 * because nothing was being loaded.
 */
type ErrorSubject =
  | {
      /** What could not be loaded, for example "the catalogue". It follows
       *  the words "We could not load". */
      what: string
      heading?: undefined
    }
  | {
      /** The whole heading, for example "We could not sign you in". */
      heading: string
      what?: undefined
    }

export function ErrorState({
  what,
  heading,
  error,
  onRetry,
  children,
}: ErrorSubject & {
  /** Whatever was thrown. Only its kind and its request id are used. */
  error: unknown
  /** Called when the person asks to try again. Leave it out when trying again
   *  cannot help. */
  onRetry?: () => void
  /** Further ways forward, shown beside the retry button. */
  children?: ReactNode
}) {
  const { advice, reference } = failureWords(error)
  return (
    <div
      role="alert"
      className="rounded-lg border border-line border-l-4 border-l-status-overdue bg-surface p-lg"
    >
      <div className="flex items-start gap-sm">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-overdue" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-base font-semibold text-ink">
            {heading ?? `We could not load ${what}`}
          </p>
          <p className="mt-xs text-sm text-slate-soft">{advice}</p>
          {(onRetry || children) && (
            <div className="mt-md flex flex-wrap items-center gap-sm">
              {onRetry && (
                <button type="button" className="btn-secondary px-md" onClick={onRetry}>
                  <RotateCw className="h-4 w-4 shrink-0" aria-hidden="true" />
                  Try again
                </button>
              )}
              {children}
            </div>
          )}
          {reference && (
            <p className="mt-md text-xs text-slate-soft">
              Reference to quote if you ring us{' '}
              <span className="select-all break-all font-mono text-ink">{reference}</span>
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
