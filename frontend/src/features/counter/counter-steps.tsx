/**
 * Where an assistant is in a task of several steps, on SC-13 and SC-14.
 *
 * The list at the top names every step and marks the one on the screen. The
 * heading of each step takes focus when the step opens, so a keyboard or
 * screen reader user lands on the new step and hears which one it is.
 *
 * The current step is marked with `aria-current` and with a heavier border,
 * and a finished one with a tick, so colour is never the only sign.
 */

import type { ReactNode, RefObject } from 'react'
import { Check } from 'lucide-react'

export function StepList({
  label,
  steps,
  current,
  allDone = false,
}: {
  /** Names the list, for example "Booking steps". */
  label: string
  steps: readonly string[]
  /** The step on the screen, counted from zero. */
  current: number
  /** True once the last step is finished too. */
  allDone?: boolean
}) {
  return (
    <ol aria-label={label} className="mb-lg flex flex-wrap gap-sm">
      {steps.map((step, index) => {
        const done = index < current || allDone
        const here = index === current && !done
        return (
          <li
            key={step}
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
              {step}
              <span className="sr-only">{done ? ', done' : here ? ', this step' : ', still to do'}</span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/** The heading of a step. It can take focus and is not a tab stop. */
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
