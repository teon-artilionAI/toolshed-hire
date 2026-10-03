/**
 * Marking a booking as a no show on SC-11, as one request.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server and released the units.
 *
 * Once the server has answered, the counter's day is marked out of date, so
 * the diary on the screen is read again and shows the booking as the server
 * now has it. A refusal does the same, because a 409 means the diary was
 * already out of date. The booking was collected, or the sweep got there first.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Reservation } from '../../shared/api/contract'
import { forgetCounterDay, rememberNoShow } from '../../shared/api/counter-queries'
import { logEvent } from '../../shared/api/log'
import { markNoShow } from '../../shared/api/reservations'
import { describeCounterFailure } from './counter-refusal'
import type { CounterRefusal } from './counter-refusal'

export interface NoShow {
  /** True while the request is in flight. */
  pending: boolean
  /** The reservation as the server answered with it, once it has. */
  reservation: Reservation | null
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  send: (reason: string) => void
  /** Put the failure away, when the person closes the question. */
  clearFailure: () => void
}

/** @param reservationId The key of the booking nobody came for. */
export function useNoShow(reservationId: string): NoShow {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [reservation, setReservation] = useState<Reservation | null>(null)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send(reason: string): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    try {
      const answered = await markNoShow(reservationId, reason)
      logEvent('info', 'counter.no_show_marked', {
        reservation_id: reservationId,
        reference: answered.reference,
        status: answered.status,
      })
      rememberNoShow(queryClient, answered)
      setReservation(answered)
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      logEvent('warn', 'counter.no_show_refused', { reservation_id: reservationId, kind: refusal.kind })
      if (refusal.kind === 'conflict') forgetCounterDay(queryClient)
      setFailure(refusal)
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  return {
    pending,
    reservation,
    failure,
    send: (reason) => void send(reason),
    clearFailure: () => setFailure(null),
  }
}
