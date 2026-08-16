/**
 * What a booking costs and what is on it.
 *
 * The rate and deposit are the snapshots taken when the booking was made,
 * never the current catalogue price, so a price rise next week does not
 * quietly rewrite what someone agreed to. The hire period is half open, so
 * the 6th to the 10th is four days and the unit is free again on the 10th.
 */

import { productModels, rentals } from '../../shared/fixtures'
import { daysBetween } from '../../shared/format'
import type { Rental, Reservation, ReservationLine } from '../../shared/types'

export function hireDays(reservation: Reservation): number {
  return daysBetween(reservation.startDate, reservation.endDate)
}

export function lineTotal(line: ReservationLine, days: number): number {
  return line.quantity * line.ratePerDaySnapshot * days
}

export function hireSubtotal(reservation: Reservation): number {
  const days = hireDays(reservation)
  return reservation.lines.reduce((sum, line) => sum + lineTotal(line, days), 0)
}

export function depositTotal(reservation: Reservation): number {
  return reservation.lines.reduce(
    (sum, line) => sum + line.quantity * line.depositPerUnitSnapshot,
    0,
  )
}

/** The catalogue entry a line points at, or undefined when the model has
 *  been withdrawn since the booking was made. */
export function modelFor(line: ReservationLine) {
  return productModels.find((model) => model.id === line.productModelId)
}

/** Human readable contents of a booking, for example
 *  "2 x Bosch GBH 2-26 DRE Rotary Hammer". */
export function itemsSummary(reservation: Reservation): string {
  return reservation.lines
    .map((line) => {
      const model = modelFor(line)
      const name = model ? `${model.manufacturer} ${model.name}` : 'Withdrawn item'
      return `${line.quantity} x ${name}`
    })
    .join(', ')
}

export function totalUnits(reservation: Reservation): number {
  return reservation.lines.reduce((sum, line) => sum + line.quantity, 0)
}

/** The hire that grew out of a booking, once it has been collected. */
export function rentalForReservation(reservation: Reservation): Rental | undefined {
  return rentals.find((rental) => rental.reservationId === reservation.id)
}
