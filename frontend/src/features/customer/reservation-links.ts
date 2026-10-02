/**
 * The addresses the reservation screens link to one another by.
 *
 * A reservation is addressed by its reference, because that is what a
 * customer quotes and what the confirmation email carries. The API reads a
 * reservation by its reference as readily as by its id.
 */

/** The list of the customer's own reservations, SC-07. */
export const MY_RESERVATIONS_PATH = '/reservations'

/** The address of SC-08 for one reservation. The reference is encoded, since
 *  by the time it is in an address it is user input. */
export function reservationHref(reference: string): string {
  return `${MY_RESERVATIONS_PATH}/${encodeURIComponent(reference)}`
}
