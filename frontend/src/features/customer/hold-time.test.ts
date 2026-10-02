/**
 * Tests for the time a hold has left. The figure, the line that is spoken,
 * and the hook that counts the seconds.
 *
 * The hook is run on a clock the test owns, so half an hour passes in an
 * instant and the test still sees every tick.
 */

import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HOLD_RAN_OUT, clockFace, spokenTimeLeft } from './hold-time'
import { useSecondsLeft } from './use-seconds-left'

const NOW = new Date('2026-03-12T08:00:00+02:00')
const IN_HALF_AN_HOUR = '2026-03-12T08:30:00+02:00'
const HOLD_SECONDS = 1800
const ONE_SECOND_MS = 1000

describe('the figure on the screen', () => {
  it.each([
    [1800, '30:00'],
    [1799, '29:59'],
    [600, '10:00'],
    [61, '01:01'],
    [9, '00:09'],
    [0, '00:00'],
  ])('writes %i seconds as %s', (seconds, face) => {
    expect(clockFace(seconds)).toBe(face)
  })
})

describe('the line that is spoken', () => {
  it('says nothing while more than ten minutes are left', () => {
    expect(spokenTimeLeft(HOLD_SECONDS)).toBe('')
    expect(spokenTimeLeft(601)).toBe('')
  })

  it.each([
    [600, '10 minutes or less left to confirm before the hold runs out.'],
    [301, '10 minutes or less left to confirm before the hold runs out.'],
    [300, '5 minutes or less left to confirm before the hold runs out.'],
    [120, '2 minutes or less left to confirm before the hold runs out.'],
    [60, '1 minute or less left to confirm before the hold runs out.'],
    [1, '1 minute or less left to confirm before the hold runs out.'],
  ])('with %i seconds left says "%s"', (seconds, sentence) => {
    expect(spokenTimeLeft(seconds)).toBe(sentence)
  })

  it('says the hold has run out at zero', () => {
    expect(spokenTimeLeft(0)).toBe(HOLD_RAN_OUT)
  })

  it('says five things in the whole half hour, and not one every second', () => {
    const spoken: string[] = []
    for (let seconds = HOLD_SECONDS; seconds >= 0; seconds -= 1) {
      const sentence = spokenTimeLeft(seconds)
      if (spoken[spoken.length - 1] !== sentence) spoken.push(sentence)
    }

    // It starts silent. Then ten, five, two and one minute, then the end.
    expect(spoken).toEqual(['', ...spoken.slice(1)])
    expect(spoken.slice(1)).toHaveLength(5)
  })
})

describe('counting the seconds', () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: NOW })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts at the whole time left and loses a second with every second', () => {
    const { result } = renderHook(() => useSecondsLeft(IN_HALF_AN_HOUR))
    expect(result.current).toBe(HOLD_SECONDS)

    act(() => {
      vi.advanceTimersByTime(ONE_SECOND_MS)
    })
    expect(result.current).toBe(HOLD_SECONDS - 1)

    act(() => {
      vi.advanceTimersByTime(59 * ONE_SECOND_MS)
    })
    expect(result.current).toBe(HOLD_SECONDS - 60)
  })

  it('reaches zero at the instant, stays there, and stops ticking', () => {
    const { result } = renderHook(() => useSecondsLeft(IN_HALF_AN_HOUR))

    act(() => {
      vi.advanceTimersByTime(HOLD_SECONDS * ONE_SECOND_MS)
    })
    expect(result.current).toBe(0)
    expect(vi.getTimerCount()).toBe(0)

    act(() => {
      vi.advanceTimersByTime(60 * ONE_SECOND_MS)
    })
    expect(result.current).toBe(0)
  })

  it('reads the clock and does not count ticks, so a tab that slept wakes up right', () => {
    const { result } = renderHook(() => useSecondsLeft(IN_HALF_AN_HOUR))

    // Five minutes pass with no tick at all, then one tick arrives.
    act(() => {
      vi.setSystemTime(new Date('2026-03-12T08:05:00+02:00'))
      vi.advanceTimersByTime(ONE_SECOND_MS)
    })

    expect(result.current).toBe(HOLD_SECONDS - 301)
  })

  it('is zero from the start for an instant that has already passed', () => {
    const { result } = renderHook(() => useSecondsLeft('2026-03-12T07:59:00+02:00'))

    expect(result.current).toBe(0)
  })

  it('follows a new instant when the hold is made again', () => {
    const { result, rerender } = renderHook(({ until }) => useSecondsLeft(until), {
      initialProps: { until: IN_HALF_AN_HOUR },
    })
    act(() => {
      vi.advanceTimersByTime(HOLD_SECONDS * ONE_SECOND_MS)
    })
    expect(result.current).toBe(0)

    rerender({ until: '2026-03-12T09:00:00+02:00' })

    expect(result.current).toBe(HOLD_SECONDS)
  })

  it.each([[null], ['not an instant']])('counts nothing for %s, and starts no timer', (until) => {
    const { result } = renderHook(() => useSecondsLeft(until))

    expect(result.current).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('stops its timer when the screen closes', () => {
    const { unmount } = renderHook(() => useSecondsLeft(IN_HALF_AN_HOUR))
    expect(vi.getTimerCount()).toBe(1)

    unmount()

    expect(vi.getTimerCount()).toBe(0)
  })
})
