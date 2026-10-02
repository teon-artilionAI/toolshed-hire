/**
 * How long a hold has left, on SC-04.
 *
 * Equipment is held for thirty minutes, and the customer has to confirm
 * inside them. The figure counts down every second, and that is for the eye.
 * It is a timer with its live setting off, so a screen reader can read it
 * when the person goes to it and never reads it by itself.
 *
 * What is spoken is not here. SC04-Hold-Step.tsx keeps one polite status on
 * the page for the whole step, and that line changes only a few times in the
 * half hour. It must never sit around this figure, or every tick would be
 * read out.
 */

import { branchClockTime } from '../../shared/today'
import { clockFace } from './hold-time'

export default function HoldCountdown({
  expiresAt,
  secondsLeft,
}: {
  /** When the hold lapses, as the API sent it. */
  expiresAt: string
  /** The seconds left, counted by the screen so it can act when they run out. */
  secondsLeft: number
}) {
  return (
    <div className="rounded bg-muted p-md">
      <p className="text-sm text-slate-soft" id="hold-countdown-label">
        Time left to confirm
      </p>
      <p
        role="timer"
        aria-live="off"
        aria-labelledby="hold-countdown-label"
        className="tabular text-3xl font-semibold text-ink"
      >
        {clockFace(secondsLeft)}
      </p>
      <p className="tabular mt-xs text-sm text-slate-soft">
        Held until {branchClockTime(expiresAt)}.
      </p>
    </div>
  )
}
