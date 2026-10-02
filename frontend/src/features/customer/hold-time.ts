/**
 * The time a hold has left, in the two ways SC-04 writes it.
 *
 * One is the figure on the screen, which changes every second. The other is
 * the line a screen reader is given, which changes only a few times in the
 * whole half hour. They are kept apart from the component that draws them so
 * each can be checked by itself.
 */

const SECONDS_PER_MINUTE = 60

/** The minutes left at which the spoken line changes, longest first. */
const SPOKEN_AT_MINUTES: readonly number[] = [10, 5, 2, 1]

export const HOLD_RAN_OUT = 'The hold has run out.'

/** Minutes and seconds as `MM:SS`, for example "29:59". */
export function clockFace(secondsLeft: number): string {
  const minutes = Math.floor(secondsLeft / SECONDS_PER_MINUTE)
  const seconds = secondsLeft % SECONDS_PER_MINUTE
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

/**
 * The line a screen reader is given for the time that is left.
 *
 * @returns The same sentence for every second between two of the marks, so it
 *   is spoken once when a mark is passed and not again until the next one.
 *   Empty while more is left than the first mark.
 */
export function spokenTimeLeft(secondsLeft: number): string {
  if (secondsLeft <= 0) return HOLD_RAN_OUT
  const mark = [...SPOKEN_AT_MINUTES]
    .reverse()
    .find((minutes) => secondsLeft <= minutes * SECONDS_PER_MINUTE)
  if (mark === undefined) return ''
  return `${mark} ${mark === 1 ? 'minute' : 'minutes'} or less left to confirm before the hold runs out.`
}
