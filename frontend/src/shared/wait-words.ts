/**
 * How long a person should wait, in words.
 *
 * The API sends the wait in seconds through `Retry-After`. Seconds below a
 * minute are written as seconds, and longer waits are rounded up to whole
 * minutes so the person is never told a time shorter than the real one.
 */

const SECONDS_PER_MINUTE = 60

export function waitInWords(seconds: number | null): string {
  if (seconds === null) return 'a few minutes'
  if (seconds < SECONDS_PER_MINUTE) return seconds === 1 ? '1 second' : `${seconds} seconds`
  const minutes = Math.ceil(seconds / SECONDS_PER_MINUTE)
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}
