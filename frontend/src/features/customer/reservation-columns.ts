/**
 * The columns of the SC-07 list, in the order they are drawn.
 *
 * On a wide screen they are the headings of the table. On a phone the table is
 * drawn as one block for each booking, the headings are not shown, and each
 * value carries its heading beside it. Both read the names from here, so the
 * two cannot drift apart.
 */

export const RESERVATION_COLUMN = {
  booking: 'Booking',
  dates: 'Hire dates',
  branch: 'Collect from',
  status: 'Status',
  total: 'Total with VAT',
  details: 'Details',
} as const

/** The headings, left to right. */
export const RESERVATION_COLUMNS: readonly string[] = Object.values(RESERVATION_COLUMN)
