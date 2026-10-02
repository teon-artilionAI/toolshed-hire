/**
 * Clearing a reservation out of the way before the basket is booked again.
 *
 * Every review of the basket used to make a new draft and leave the last one
 * where it was, so a customer who went back and forth ended up with a list of
 * drafts. The basket now remembers the reservation that was set aside, and
 * this decides what becomes of it.
 *
 * A draft that still fits the basket is read back and carried on with, so
 * looking at the basket and reviewing it again makes nothing new. One the
 * basket has changed underneath is cancelled first. If that one was holding
 * equipment, cancelling it also frees the units for the booking that follows.
 *
 * Whether a reservation may be cancelled is the server's answer. A conflict or
 * a 404 means there is nothing left to cancel, and the booking goes on. Any
 * other failure is thrown, so the person is told and can try again.
 */

import type { Reservation } from '../../shared/api/contract'
import { logEvent } from '../../shared/api/log'
import { cancelReservation, getReservation } from '../../shared/api/reservations'
import type { SetAsideReservation } from '../../shared/basket-store'
import { describeBookingFailure, isNotFound } from './booking-refusal'

/**
 * Cancel a reservation the person is giving up.
 *
 * @returns The cancelled reservation, or null when the server says it was
 *   already over or is not there, which leaves nothing to cancel.
 * @throws Whatever the request threw, when it failed for any other reason.
 */
export async function cancelIfItStillStands(reservationId: string): Promise<Reservation | null> {
  try {
    return await cancelReservation(reservationId, null)
  } catch (cause) {
    const alreadyOver = describeBookingFailure(cause).kind === 'conflict'
    if (!alreadyOver && !isNotFound(cause)) throw cause
    logEvent('info', 'booking.nothing_left_to_cancel', {
      reservation_id: reservationId,
      because: alreadyOver ? 'already over' : 'not found',
    })
    return null
  }
}

/** Read a reservation back, or null when it is not there any more. */
async function readIfItIsThere(reservationId: string): Promise<Reservation | null> {
  try {
    return await getReservation(reservationId)
  } catch (cause) {
    if (!isNotFound(cause)) throw cause
    logEvent('info', 'booking.set_aside_reservation_gone', { reservation_id: reservationId })
    return null
  }
}

/**
 * Deal with the reservation that was set aside.
 *
 * @returns The reservation to carry on with, when it is still a draft and the
 *   basket has not changed since it was made. Null once it is out of the way
 *   and a new reservation has to be made.
 * @throws Whatever a request threw, when the reservation could not be read
 *   back or cancelled.
 */
export async function settleSetAside(aside: SetAsideReservation): Promise<Reservation | null> {
  if (aside.fitsBasket) {
    const standing = await readIfItIsThere(aside.reservationId)
    if (standing === null) return null
    if (standing.status === 'DRAFT') {
      logEvent('info', 'booking.draft_carried_on', { reservation_id: standing.id })
      return standing
    }
    if (!standing.canCancel) return null
  }
  const cancelled = await cancelIfItStillStands(aside.reservationId)
  if (cancelled !== null) {
    logEvent('info', 'booking.replaced_reservation_cancelled', { reservation_id: cancelled.id })
  }
  return null
}
