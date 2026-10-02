/**
 * Turning the hire basket into a booking, one request at a time.
 *
 * There are three requests and SC-04 shows what each one answered. Creating
 * the reservation prices the basket. Holding it takes the equipment for thirty
 * minutes. Confirming it books the hire. The server answers each with the
 * whole reservation, and what the screen shows next is read off that answer.
 * Nothing here decides what a reservation may do. The buttons come from
 * `canHold`, `canConfirm` and `canCancel`.
 *
 * Only one request runs at a time. A second press while one is in flight does
 * nothing, and none is ever repeated by itself, because a request that timed
 * out may still have reached the server.
 *
 * The basket remembers the reservation that was made from it. So a reload in
 * the middle of a booking reads that reservation back and carries on from
 * where it stands, and does not make a second one that would compete with the
 * first for the same equipment.
 *
 * Going back to the basket from the review sets the draft aside. Reviewing
 * again carries on with that draft when the basket has not changed, and
 * cancels it before making another when it has. That is in
 * booking-set-aside.ts, and it is what keeps a change of mind from leaving a
 * draft behind each time.
 */

import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { CreateReservationRequest, Reservation } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import { rememberReservation, reservationQueries } from '../../shared/api/reservation-queries'
import { confirmReservation, createReservation, holdReservation } from '../../shared/api/reservations'
import {
  basketSnapshot,
  clearBasket,
  forgetBookingUnderWay,
  forgetReservationSetAside,
  noteBookingUnderWay,
  setBookingAside,
} from '../../shared/basket-store'
import type { Basket } from '../../shared/basket-store'
import { describeBookingFailure, isNotFound } from './booking-refusal'
import type { BookingRefusal } from './booking-refusal'
import { cancelIfItStillStands, settleSetAside } from './booking-set-aside'

/** What SC-04 is showing. The basket, then one view for each request that worked. */
export type BookingView = 'basket' | 'review' | 'hold' | 'confirmed'

/** The requests a person can start. `release` gives a hold up to change the basket. */
export type BookingAction = 'review' | 'hold' | 'confirm' | 'release'

export interface BookingFailure {
  action: BookingAction
  refusal: BookingRefusal
}

export interface Booking {
  view: BookingView
  /** The reservation the view is about. Null while the view is the basket. */
  reservation: Reservation | null
  /** The request in flight, or null. Every button is disabled while there is one. */
  pending: BookingAction | null
  /** Why the last request did not work, until the next one starts or the
   *  basket changes. A refusal is about the basket as it was. */
  failure: BookingFailure | null
  /** The server's sentence when the account may not book. Once it is set the
   *  screen offers no way to book. */
  blockedBecause: string | null
  /** True once the server has said the hold was gone when a confirm arrived. */
  holdLapsed: boolean
  /** A booking that was under way before a reload is being read back. */
  resume: { loading: boolean; error: unknown; retry: () => void }
  review: () => void
  hold: () => void
  confirm: () => void
  /** Make a new reservation from the basket and hold that. A lapsed hold
   *  cannot be held again, so a new one is the only way to carry on. */
  holdAgain: () => void
  /**
   * Go back to the basket. A draft is set aside, to be carried on with or
   * cancelled when the basket is reviewed again.
   *
   * @param releaseHold True when the equipment is still held. The hold is then
   *   cancelled first, when the server says it can be, so the equipment is
   *   free for the next attempt and not kept from it by this one.
   */
  changeBasket: (releaseHold?: boolean) => void
}

function requestFrom(basket: Basket): CreateReservationRequest {
  return {
    branchCode: basket.branchCode,
    from: basket.from,
    to: basket.to,
    lines: basket.lines.map(({ modelSlug, quantity }) => ({ modelSlug, quantity })),
    customerProfileId: null,
    notes: null,
  }
}

/** The view a reservation that is under way belongs to, or null when the
 *  booking is over and the basket is all there is to show. */
function viewOf(reservation: Reservation): BookingView | null {
  if (reservation.status === 'DRAFT') return 'review'
  if (reservation.status === 'HELD' || reservation.status === 'EXPIRED') return 'hold'
  if (reservation.status === 'CONFIRMED') return 'confirmed'
  return null
}

/**
 * @param basket The basket as it stands.
 * @param mayBook False for a visitor and for staff. Nothing is asked of the
 *   API until a customer is signed in.
 */
export function useBooking(basket: Basket, mayBook: boolean): Booking {
  const queryClient = useQueryClient()
  const [made, setMade] = useState<Reservation | null>(null)
  const [confirmed, setConfirmed] = useState<Reservation | null>(null)
  const [pending, setPending] = useState<BookingAction | null>(null)
  const [failed, setFailed] = useState<(BookingFailure & { basket: Basket }) | null>(null)
  const [blockedBecause, setBlockedBecause] = useState<string | null>(null)
  const [lapsedId, setLapsedId] = useState<string | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  const underWayId = basket.reservationId
  const madeHere = made !== null && made.id === underWayId ? made : null
  const resumed = useQuery({
    ...reservationQueries.detail(underWayId ?? ''),
    enabled: mayBook && underWayId !== null && madeHere === null,
  })
  const underWay = underWayId === null ? null : (madeHere ?? resumed.data ?? null)
  const underWayView = underWay === null ? null : viewOf(underWay)
  const resumeLost = isNotFound(resumed.error)

  // A booking that was confirmed before the reload is done. Keep its answer,
  // because emptying the basket below also forgets which reservation it was.
  if (confirmed === null && underWay !== null && underWayView === 'confirmed') setConfirmed(underWay)

  useEffect(() => {
    if (confirmed !== null) clearBasket()
  }, [confirmed])

  // A reservation that has moved on by other means, or is not this person's,
  // is nothing to carry on with. The basket stays and can be booked afresh.
  useEffect(() => {
    if ((underWay !== null && underWayView === null) || resumeLost) forgetBookingUnderWay()
  }, [underWay, underWayView, resumeLost])

  async function run(action: BookingAction, work: () => Promise<Reservation | null>): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(action)
    setFailed(null)
    try {
      const answer = await work()
      if (answer === null) return
      rememberReservation(queryClient, answer)
      if (answer.status === 'CONFIRMED') {
        setConfirmed(answer)
        return
      }
      noteBookingUnderWay(answer.id)
      setMade(answer)
    } catch (cause) {
      const refusal = describeBookingFailure(cause)
      if (refusal.kind === 'accountOnHold') setBlockedBecause(refusal.detail)
      if (action === 'confirm' && refusal.kind === 'conflict') setLapsedId(underWayId)
      setFailed({ action, refusal, basket: basketSnapshot() })
    } finally {
      inFlight.current = false
      setPending(null)
    }
  }

  function backToBasket(): void {
    // A draft is kept in mind, because the next review either carries on with
    // it or has to cancel it. Anything else here is released, lapsed or lost,
    // and leaves nothing to come back to.
    if (underWayView === 'review') setBookingAside()
    else forgetBookingUnderWay()
    setMade(null)
    setFailed(null)
  }

  const view: BookingView = confirmed !== null ? 'confirmed' : (underWayView ?? 'basket')

  return {
    view,
    reservation: confirmed ?? (underWayView === null ? null : underWay),
    pending,
    failure: failed !== null && failed.basket === basket ? failed : null,
    blockedBecause,
    holdLapsed: lapsedId !== null && lapsedId === underWayId,
    resume: {
      loading: queryPhase(resumed) === 'loading',
      error: queryPhase(resumed) === 'failed' && !resumeLost ? resumed.error : null,
      retry: () => void resumed.refetch(),
    },
    review: () =>
      void run('review', async () => {
        if (basket.setAside !== null) {
          const stillStanding = await settleSetAside(basket.setAside)
          if (stillStanding !== null) return stillStanding
          forgetReservationSetAside()
        }
        return createReservation(requestFrom(basket))
      }),
    hold: () => {
      if (underWay !== null) void run('hold', () => holdReservation(underWay.id))
    },
    confirm: () => {
      if (underWay !== null) void run('confirm', () => confirmReservation(underWay.id))
    },
    holdAgain: () =>
      void run('hold', async () => {
        // The new draft is noted before the hold is asked for. If the hold is
        // refused, the screen is then on the draft that was refused.
        const draft = await createReservation(requestFrom(basket))
        rememberReservation(queryClient, draft)
        noteBookingUnderWay(draft.id)
        setMade(draft)
        return holdReservation(draft.id)
      }),
    changeBasket: (releaseHold = false) => {
      if (!releaseHold || underWay === null || !underWay.canCancel) {
        backToBasket()
        return
      }
      void run('release', async () => {
        // When the hold was already gone there is nothing left to release and
        // the basket can be changed. Any other failure is thrown, and the
        // person is told about it.
        const released = await cancelIfItStillStands(underWay.id)
        if (released !== null) rememberReservation(queryClient, released)
        backToBasket()
        return null
      })
    },
  }
}
