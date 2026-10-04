/**
 * A booking short of units on SC-14, after the owner released one.
 *
 * The checkout says how many units the booking still needs, `unitsShort`, and
 * while that is above zero it cannot go out. This says how many are missing
 * and offers any member of staff "Find a replacement unit". The button says
 * beside it what it does, and one press posts the reallocation, which sets
 * aside free units of the same models through the same path a hold takes. The
 * answer is the booking with its new units, and the checkout is read again.
 *
 * When nothing is free the server answers 409 naming the model and the dates,
 * and the screen shows that sentence. A 403, at another branch, shows the
 * server's sentence as well.
 */

import { useQueryClient } from '@tanstack/react-query'
import { PackageSearch } from 'lucide-react'
import type { Reservation, ReservationCheckout } from '../../shared/api/contract'
import { rememberReservation } from '../../shared/api/reservation-queries'
import { reallocateReservation } from '../../shared/api/reservations'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { countOf } from './counter-labels'
import { useAllocationWrite } from './use-allocation-write'

const HEADING_ID = 'units-short-heading'
const WHAT_IT_DOES_ID = 'units-short-what-it-does'

export function UnitsShort({
  checkout,
  onReallocated,
}: {
  checkout: ReservationCheckout
  /** Called with the booking the server answered with. */
  onReallocated: (reservation: Reservation) => void
}) {
  const queryClient = useQueryClient()
  const write = useAllocationWrite<Reservation>(checkout.reference, 'reallocation')
  const failure = write.failure
  const missing = checkout.unitsShort
  const label = missing === 1 ? 'Find a replacement unit' : 'Find replacement units'

  function find() {
    write.send(
      async () => {
        const reservation = await reallocateReservation(checkout.reservationId)
        rememberReservation(queryClient, reservation)
        return reservation
      },
      onReallocated,
    )
  }

  return (
    <section aria-labelledby={HEADING_ID} className="card mt-lg p-lg">
      <h2 id={HEADING_ID} className="text-lg font-semibold text-ink">
        {countOf(missing, 'unit is', 'units are')} missing from this booking
      </h2>
      <p id={WHAT_IT_DOES_ID} className="mt-xs text-sm text-ink">
        {checkout.reference} needs {countOf(missing, 'more unit', 'more units')} before it can go out. Finding a
        replacement sets aside a free unit of the same model at {checkout.branchName} for the same dates, the way a
        hold does, and reads the booking again.
      </p>
      <div className="mt-md">
        <button
          type="button"
          className="btn-primary px-md"
          disabled={write.pending}
          aria-describedby={WHAT_IT_DOES_ID}
          onClick={find}
        >
          <PackageSearch className="h-4 w-4 shrink-0" aria-hidden="true" />
          {write.pending ? 'Looking for a free unit' : label}
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? 'Looking for a free unit, please wait.' : ''}
      </p>
      {failure !== null && failure.kind !== 'fault' && (
        <div className="mt-md">
          <Notice tone="error" title="No replacement was set aside">
            <p>{failure.detail}</p>
          </Notice>
        </div>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading="We could not look for a replacement" error={failure.error} onRetry={find} />
        </div>
      )}
    </section>
  )
}
