/**
 * The handover on SC-14, as one request.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server. The API answers a repeat
 * for a reservation that is already out with the hire it made the first time,
 * so a person who presses again after a timeout is shown that hire.
 *
 * Once the hire is made, everything cached about reservations is marked out of
 * date, because this one is now collected.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { checkOutReservation } from '../../shared/api/checkout'
import type { CheckoutRequest, Rental } from '../../shared/api/contract'
import { forgetReservationsAfterCheckout } from '../../shared/api/counter-queries'
import { logEvent } from '../../shared/api/log'
import { describeCounterFailure } from './counter-refusal'
import type { CounterRefusal } from './counter-refusal'

export interface Handover {
  /** True while the request is in flight. */
  pending: boolean
  /** The hire the server made, once it has made it. */
  rental: Rental | null
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  send: (body: CheckoutRequest) => void
  /** Put the failure away, when the person goes back to change something. */
  clearFailure: () => void
}

/** @param idOrReference The key or the reference of the reservation. */
export function useHandover(idOrReference: string): Handover {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [rental, setRental] = useState<Rental | null>(null)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send(body: CheckoutRequest): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    try {
      const made = await checkOutReservation(idOrReference, body)
      logEvent('info', 'counter.checked_out', {
        reservation: idOrReference,
        rental_id: made.id,
        units: made.items.length,
      })
      forgetReservationsAfterCheckout(queryClient)
      setRental(made)
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      logEvent('warn', 'counter.checkout_refused', { reservation: idOrReference, kind: refusal.kind })
      setFailure(refusal)
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  return {
    pending,
    rental,
    failure,
    send: (body) => void send(body),
    clearFailure: () => setFailure(null),
  }
}
