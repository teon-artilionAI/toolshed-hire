/**
 * Where the counter screens send a person, written in one place.
 *
 * A key or a reference is user input by the time it is put in an address, so
 * it is always encoded.
 */

/** SC-12, where a customer is found or registered. */
export const CUSTOMERS_PATH = '/counter/customers'

/** SC-10, the counter's home. */
export const COUNTER_HOME_PATH = '/counter'

/** SC-11, the branch diary. */
export const DIARY_PATH = '/counter/diary'

/** SC-13, a new booking. Without a customer it asks for one first. */
export const NEW_BOOKING_PATH = '/counter/booking'

/** The query parameter SC-13 carries its customer in, so a reload keeps them. */
export const CUSTOMER_PARAMETER = 'customer'

/** SC-13, a new booking for one customer. */
export function bookingHref(customerId: string): string {
  return `/counter/booking?${CUSTOMER_PARAMETER}=${encodeURIComponent(customerId)}`
}

/** SC-12 with one customer chosen, so their bookings are on the screen. */
export function customerHref(customerId: string): string {
  return `${CUSTOMERS_PATH}?${CUSTOMER_PARAMETER}=${encodeURIComponent(customerId)}`
}

/** SC-14, the handover of one reservation, by its key or its reference. */
export function checkoutHref(reservationIdOrReference: string): string {
  return `/counter/checkout/${encodeURIComponent(reservationIdOrReference)}`
}

/** SC-15, the hire a reservation became, by its key. */
export function rentalHref(rentalId: string): string {
  return `/counter/return/${encodeURIComponent(rentalId)}`
}
