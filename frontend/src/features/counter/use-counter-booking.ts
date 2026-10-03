/**
 * A booking at the counter, one request at a time.
 *
 * It is the same three requests an online booking makes, on the same routes,
 * with the customer named because staff book on a customer's behalf. Making
 * the reservation prices it. Holding it sets the units aside. Confirming it
 * books the hire. The server answers each with the whole reservation, and the
 * step the screen shows is read off that answer. Nothing here decides what a
 * reservation may do. The buttons come from `canHold`, `canConfirm` and
 * `canCancel`.
 *
 * Only one request runs at a time. A second press while one is in flight does
 * nothing, and none is ever repeated by itself, because a request that timed
 * out may still have reached the server.
 *
 * Going back to change the tools cancels the reservation first, when the
 * server says it can be cancelled, so a hold gives its units back at once and
 * a priced draft is not left behind for every change of mind. A conflict or a
 * 404 on that cancellation means there was nothing left to cancel.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Reservation } from '../../shared/api/contract'
import { logEvent } from '../../shared/api/log'
import { rememberReservation } from '../../shared/api/reservation-queries'
import {
  cancelReservation,
  confirmReservation,
  createReservation,
  holdReservation,
} from '../../shared/api/reservations'
import { toReservationRequest } from './booking-draft'
import type { BookingDraft } from './booking-draft'
import { describeCounterFailure, isNotFound } from './counter-refusal'
import type { CounterRefusal } from './counter-refusal'

/** What SC-13 is showing. The tools, then one view for each request that worked. */
export type CounterBookingView = 'lines' | 'review' | 'held' | 'confirmed'

/** The requests an assistant can start. `release` gives a reservation up to change the tools. */
export type CounterBookingAction = 'price' | 'hold' | 'confirm' | 'release'

export interface CounterBookingFailure {
  action: CounterBookingAction
  refusal: CounterRefusal
}

export interface CounterBooking {
  view: CounterBookingView
  /** The reservation the view is about. Null while the view is the tools. */
  reservation: Reservation | null
  /** The request in flight, or null. Every button is disabled while there is one. */
  pending: CounterBookingAction | null
  /** Why the last request did not work, until the next one starts. */
  failure: CounterBookingFailure | null
  /** The server's sentence when the customer may not book. Once it is set the
   *  screen offers no way to book. */
  blockedBecause: string | null
  price: (draft: BookingDraft) => void
  hold: () => void
  confirm: () => void
  /** Go back to the tools, cancelling the reservation first when it can be. */
  changeTools: () => void
  /** Start another booking for the same customer, from nothing. */
  startAgain: () => void
}

function viewOf(reservation: Reservation | null): CounterBookingView {
  if (reservation === null) return 'lines'
  if (reservation.status === 'DRAFT') return 'review'
  if (reservation.status === 'CONFIRMED') return 'confirmed'
  return 'held'
}

/**
 * Cancel a reservation the assistant is giving up.
 *
 * @throws Whatever the request threw, unless the server said there was
 *   nothing left to cancel.
 */
async function giveUp(reservation: Reservation): Promise<Reservation | null> {
  if (!reservation.canCancel) return null
  try {
    return await cancelReservation(reservation.id, null)
  } catch (cause) {
    const alreadyOver = describeCounterFailure(cause).kind === 'conflict'
    if (!alreadyOver && !isNotFound(cause)) throw cause
    logEvent('info', 'counter.nothing_left_to_cancel', { reservation_id: reservation.id })
    return null
  }
}

/**
 * @param customerProfileId The customer the booking is for.
 * @param branchCode The branch the assistant works at, where it is collected.
 */
export function useCounterBooking(customerProfileId: string, branchCode: string): CounterBooking {
  const queryClient = useQueryClient()
  const [reservation, setReservation] = useState<Reservation | null>(null)
  const [pending, setPending] = useState<CounterBookingAction | null>(null)
  const [failure, setFailure] = useState<CounterBookingFailure | null>(null)
  const [blockedBecause, setBlockedBecause] = useState<string | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function run(
    action: CounterBookingAction,
    work: () => Promise<Reservation | null>,
  ): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(action)
    setFailure(null)
    try {
      const answer = await work()
      if (answer !== null) rememberReservation(queryClient, answer)
      setReservation(action === 'release' ? null : answer)
      logEvent('info', 'counter.booking_step_done', {
        action,
        reservation_id: answer?.id ?? null,
        status: answer?.status ?? null,
      })
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      if (refusal.kind === 'accountOnHold') setBlockedBecause(refusal.detail)
      setFailure({ action, refusal })
    } finally {
      inFlight.current = false
      setPending(null)
    }
  }

  return {
    view: viewOf(reservation),
    reservation,
    pending,
    failure,
    blockedBecause,
    price: (draft) =>
      void run('price', () => createReservation(toReservationRequest(draft, branchCode, customerProfileId))),
    hold: () => {
      if (reservation !== null) void run('hold', () => holdReservation(reservation.id))
    },
    confirm: () => {
      if (reservation !== null) void run('confirm', () => confirmReservation(reservation.id))
    },
    changeTools: () => {
      if (reservation === null) return
      void run('release', () => giveUp(reservation))
    },
    startAgain: () => {
      if (inFlight.current) return
      setReservation(null)
      setFailure(null)
    },
  }
}
