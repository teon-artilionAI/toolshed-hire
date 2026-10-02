/**
 * How many seconds are left until an instant, counted down once a second.
 *
 * The answer is worked out from the clock on every tick and is never
 * decremented, so a tab that was asleep for five minutes wakes up showing the
 * right figure and not one that is five minutes behind.
 */

import { useEffect, useState } from 'react'

const TICK_MS = 1000
const MS_PER_SECOND = 1000

/** Whole seconds from `now` until `until`, rounded up, and never below zero. */
function secondsBetween(now: number, until: number): number {
  return Math.max(0, Math.ceil((until - now) / MS_PER_SECOND))
}

/**
 * @param until An ISO 8601 instant, or null when there is nothing to count to.
 * @returns The seconds left, zero once the instant has passed, or null when
 *   there is no instant to count to.
 */
export function useSecondsLeft(until: string | null): number | null {
  const instant = until === null ? Number.NaN : Date.parse(until)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (Number.isNaN(instant)) return
    // Read the clock at once, so a new instant is not measured against the
    // moment the last one was read.
    setNow(Date.now())
    const timer = window.setInterval(() => {
      const current = Date.now()
      setNow(current)
      if (current >= instant) window.clearInterval(timer)
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [instant])

  return Number.isNaN(instant) ? null : secondsBetween(now, instant)
}
