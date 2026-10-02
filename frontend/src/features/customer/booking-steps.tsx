/**
 * Where a person is in a booking, on SC-04.
 *
 * A booking takes three requests, and each one that works opens the next view.
 * The list at the top names all three and marks the one on the screen. The
 * heading of each view takes focus when the view opens, so a keyboard or
 * screen reader user lands on the new step and hears which one it is.
 *
 * The current step is marked with `aria-current` and with a heavier border,
 * and a finished one with a tick, so colour is never the only sign.
 */

import type { ReactNode, RefObject } from 'react'
import { Check } from 'lucide-react'
import type { BookingView } from './use-booking'

const STEPS: readonly { view: BookingView; label: string }[] = [
  { view: 'review', label: 'Review the cost' },
  { view: 'hold', label: 'Hold the equipment' },
  { view: 'confirmed', label: 'Confirm the hire' },
]

export function BookingSteps({ view }: { view: BookingView }) {
  const current = STEPS.findIndex((step) => step.view === view)
  return (
    <ol aria-label="Booking steps" className="mb-lg flex flex-wrap gap-sm">
      {STEPS.map((step, index) => {
        const done = index < current || view === 'confirmed'
        const here = index === current && !done
        return (
          <li
            key={step.view}
            aria-current={index === current ? 'step' : undefined}
            className={`flex min-h-[2.75rem] items-center gap-sm rounded border px-md py-sm text-sm ${
              here
                ? 'border-2 border-ink bg-surface font-semibold text-ink'
                : 'border-line bg-surface text-slate-soft'
            }`}
          >
            {done ? (
              <Check className="h-4 w-4 shrink-0" aria-hidden="true" />
            ) : (
              <span className="tabular" aria-hidden="true">
                {index + 1}
              </span>
            )}
            <span>
              <span className="sr-only">Step {index + 1}, </span>
              {step.label}
              <span className="sr-only">{done ? ', done' : here ? ', this step' : ', still to do'}</span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/** The heading of a view. It can take focus and is not a tab stop. */
export function StepHeading({
  headingRef,
  children,
}: {
  headingRef: RefObject<HTMLHeadingElement | null>
  children: ReactNode
}) {
  return (
    <h2 ref={headingRef} tabIndex={-1} className="mb-md text-lg font-semibold text-ink">
      {children}
    </h2>
  )
}
