/**
 * One change to the units of a booking on SC-14, as one request. The owner's
 * release of a unit, or the counter's search for a replacement.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server and moved a unit.
 *
 * Whatever the answer, the checkout of the booking is marked out of date, so
 * the screen reads it again and shows the units and the shortfall as the
 * server now has them. A refusal does the same, because a 409 means the
 * booking moved on since it was read. The owner's figures and the trail are
 * marked out of date too, because a release is recorded there.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { forgetOwnerFigures } from '../../shared/api/admin-queries'
import { forgetAfterAllocationChange } from '../../shared/api/counter-queries'
import { logEvent } from '../../shared/api/log'
import { describeCounterFailure } from './counter-refusal'
import type { CounterRefusal } from './counter-refusal'

/** What the change is, for the log. */
export type AllocationWriteKind = 'release' | 'reallocation'

export interface AllocationWrite<Result> {
  /** True while the request is in flight. */
  pending: boolean
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  /**
   * Send the change. Nothing happens while another is in flight.
   *
   * @param write Makes the one request.
   * @param onDone Called with what the server answered.
   */
  send: (write: () => Promise<Result>, onDone: (result: Result) => void) => void
  /** Put the failure away, when the person closes the question. */
  clearFailure: () => void
}

/**
 * @param subject The booking or the allocation the change is about, for the log.
 * @param kind What the change is, for the log.
 */
export function useAllocationWrite<Result>(subject: string, kind: AllocationWriteKind): AllocationWrite<Result> {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send(write: () => Promise<Result>, onDone: (result: Result) => void): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    try {
      const result = await write()
      logEvent('info', 'counter.allocation_changed', { kind, subject })
      forgetAfterAllocationChange(queryClient)
      forgetOwnerFigures(queryClient)
      onDone(result)
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      logEvent('warn', 'counter.allocation_change_refused', { kind, subject, refusal: refusal.kind })
      if (refusal.kind === 'conflict') forgetAfterAllocationChange(queryClient)
      setFailure(refusal)
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  return {
    pending,
    failure,
    send: (write, onDone) => void send(write, onDone),
    clearFailure: () => setFailure(null),
  }
}
