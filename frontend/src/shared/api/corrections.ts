/**
 * The owner's corrections. Waiving a charge, reversing one, adjusting a hire,
 * and releasing a unit a booking holds.
 *
 * Every route here is for an administrator, and the API refuses anyone else
 * with a 403. Each takes a written reason, which the server keeps with the
 * charge and in the audit event of the same unit of work. A charge correction
 * answers with the whole hire as the server now has it, its deposit, balance
 * and status worked out again by the settlement code that already exists.
 * Nothing here or above it adds up a figure.
 *
 * A settled charge is never changed. A reversal is a new charge that points
 * back at the original, so both stay on the hire.
 *
 * Each write is sent once for each press of a button and never repeated by the
 * client, because a request that timed out may still have reached the server.
 */

import { api } from './client'
import type { CorrectionReasonRequest, HireAdjustmentRequest, Money, Rental } from './contract'
import { readRental } from './rental-read'

/** The fewest characters a reason may have. The server refuses fewer with a 422. */
export const MIN_REASON_LENGTH = 5

/** The most characters a reason may have. The server refuses more with a 422. */
export const MAX_REASON_LENGTH = 200

const CHARGES_ENDPOINT = '/admin/charges'
const RENTALS_ENDPOINT = '/admin/rentals'
const ALLOCATIONS_ENDPOINT = '/admin/allocations'

/** An id is user input by the time it reaches here, so it is always encoded. */
function under(base: string, id: string, action: string): string {
  return `${base}/${encodeURIComponent(id)}/${action}`
}

/**
 * The release route's answer is not one the screen reads. The contract names
 * no body for it, so whatever comes back is accepted and the screen reads the
 * checkout preview again for what changed.
 */
function ignoreTheBody(): void {}

/**
 * POST /api/admin/charges/{id}/waiver. A pending charge becomes waived.
 *
 * @throws ApiError with status 409 when the charge is not pending, 422 when the
 *   reason is refused, and 403 for anyone but an administrator.
 */
export function waiveCharge(chargeId: string, reason: string): Promise<Rental> {
  const body: CorrectionReasonRequest = { reason }
  return api.post(under(CHARGES_ENDPOINT, chargeId, 'waiver'), body, readRental)
}

/**
 * POST /api/admin/charges/{id}/reversal. A new charge of the same type with
 * the amounts the other way, pointing back at a settled one.
 *
 * @throws ApiError with status 409 when the charge is not settled or has been
 *   reversed already, 422 when the reason is refused, and 403 for anyone but an
 *   administrator.
 */
export function reverseCharge(chargeId: string, reason: string): Promise<Rental> {
  const body: CorrectionReasonRequest = { reason }
  return api.post(under(CHARGES_ENDPOINT, chargeId, 'reversal'), body, readRental)
}

/**
 * POST /api/admin/rentals/{id}/adjustments. A new adjustment charge, VAT
 * inclusive, positive or negative.
 *
 * @throws ApiError with status 422 naming `amountIncVat` or `reason` when
 *   either is refused, and 403 for anyone but an administrator.
 */
export function adjustHire(rentalId: string, amountIncVat: Money, reason: string): Promise<Rental> {
  const body: HireAdjustmentRequest = { amountIncVat, reason }
  return api.post(under(RENTALS_ENDPOINT, rentalId, 'adjustments'), body, readRental)
}

/**
 * POST /api/admin/allocations/{id}/release. Frees one unit a booking holds.
 * The booking is then short a unit until it is reallocated.
 *
 * @throws ApiError with status 409 when the allocation is not active or its
 *   unit is already on hire, 422 when the reason is refused, and 403 for
 *   anyone but an administrator.
 */
export function releaseAllocation(allocationId: string, reason: string): Promise<void> {
  const body: CorrectionReasonRequest = { reason }
  return api.post(under(ALLOCATIONS_ENDPOINT, allocationId, 'release'), body, ignoreTheBody)
}
