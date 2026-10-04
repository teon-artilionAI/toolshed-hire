/**
 * SC-14 Checkout and Deposit.
 *
 * The counter side of handing equipment over, for one confirmed reservation.
 * The address carries the reservation's key or its reference. The screen reads
 * what the counter needs from the API, and the server decides whether it can
 * go out now. When it cannot, the screen shows the server's sentence and no
 * form. When it already has, the screen says so and links to the hire.
 *
 * For each unit the assistant confirms the tag and records the condition, the
 * accessories and the meter. Then the deposit to take is shown and the
 * customer signs the agreement. One button asks the question, which says in
 * words what is about to happen, and one button answers it and records the
 * handover. That is one request, and the server makes the hire, the charges
 * and the deposit in one go.
 *
 * The handover lives above everything else on the screen, so the hire it made
 * stays on the screen when the reservation is read again and comes back
 * collected. When the step changes, focus moves to the heading of the new one.
 *
 * A signed in administrator can release any unit the booking holds, from the
 * unit itself, through SC14-Unit-Release.tsx. A booking short of units cannot
 * go out, and any member of staff can then look for a replacement, through
 * SC14-Units-Short.tsx. What either did is said at the top in a notice that
 * takes focus, and the booking is read again.
 */

import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { CheckoutUnit, Reservation } from '../../shared/api/contract'
import { checkoutQueries } from '../../shared/api/counter-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { formatDate } from '../../shared/format'
import { Notice, PageHeader, StatusPill } from '../../shared/ui'
import { useSession } from '../../shared/use-session'
import { CUSTOMERS_PATH } from './counter-links'
import { isNotFound } from './counter-refusal'
import { StepList } from './counter-steps'
import { CheckoutForm } from './SC14-Checkout-Form'
import type { CheckoutStage } from './SC14-Checkout-Form'
import { AlreadyOut, CannotCheckOut, HandedOver } from './SC14-CheckoutFinish'
import { ReleaseUnit, SetAsideUnits } from './SC14-Unit-Release'
import { UnitsShort } from './SC14-Units-Short'
import { useHandover } from './use-handover'

/** What a change to the units of the booking did, in words. */
interface UnitsChanged {
  title: string
  body: string
}

function releasedWords(unit: CheckoutUnit, reference: string): UnitsChanged {
  return {
    title: `${unit.assetTag} is released`,
    body: `It is back on the shelf, and ${reference} is short a unit until it is reallocated.`,
  }
}

function reallocatedWords(reservation: Reservation): UnitsChanged {
  const tags = reservation.lines.flatMap((line) => line.assetTags)
  return {
    title: `${reservation.reference} has its units again`,
    body: tags.length === 0 ? 'The server set no unit aside.' : `Set aside now: ${tags.join(', ')}.`,
  }
}

const STEPS = ['Check each unit', 'Hand it over', 'Out on hire'] as const

const STEP_OF: Record<CheckoutStage | 'done', number> = { filling: 0, asking: 1, done: 2 }

/** What the step change means, for a person who cannot see it. */
function outcome(shown: CheckoutStage | 'done', rentalReference: string | null): string {
  if (shown === 'done' && rentalReference !== null) return `The equipment is out on hire ${rentalReference}.`
  if (shown === 'asking') return 'Everything is recorded. Read the question to the customer, then hand it over.'
  return ''
}

export default function CheckoutAndDeposit() {
  const { reservationId = '' } = useParams()
  const { role } = useSession()
  const owner = role === 'admin'
  const checkout = useQuery({ ...checkoutQueries.detail(reservationId), enabled: reservationId !== '' })
  const handover = useHandover(reservationId)
  const [stage, setStage] = useState<CheckoutStage>('filling')
  const [unitsChanged, setUnitsChanged] = useState<UnitsChanged | null>(null)
  const phase = queryPhase(checkout)
  const data = checkout.data
  const shown = handover.rental !== null ? 'done' : stage

  // A change to the units replaces part of the screen, so focus goes to what it did.
  const changedRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (unitsChanged !== null) changedRef.current?.focus()
  }, [unitsChanged])

  // The form is where the page opens, and the router has already put focus on
  // the page. Only a change of step moves it to the heading of the new step.
  const heading = useRef<HTMLHeadingElement>(null)
  const shownBefore = useRef(shown)
  useEffect(() => {
    if (shownBefore.current === shown) return
    shownBefore.current = shown
    heading.current?.focus()
  }, [shown])

  if (phase === 'failed' && isNotFound(checkout.error)) {
    return (
      <>
        <PageHeader screenId="SC-14" title="We cannot find that booking" />
        <Notice tone="error" title={`No booking matches "${reservationId}"`}>
          <p>Check the reference against the paperwork, or find the customer and open the booking from there.</p>
          <Link to={CUSTOMERS_PATH} className="btn-secondary mt-sm px-md">
            Find a customer
          </Link>
        </Notice>
      </>
    )
  }

  const ready = data !== undefined && data.rentalId === null && data.canCheckOut
  return (
    <>
      <PageHeader
        screenId="SC-14"
        title="Checkout and deposit"
        subtitle={
          data
            ? `${data.reference} for ${data.customer.displayName}. Out ${formatDate(data.from)}, back ${formatDate(data.to)}, from ${data.branchName}.`
            : undefined
        }
        actions={data ? <StatusPill status={data.status} /> : undefined}
      />
      {(ready || handover.rental !== null) && (
        <StepList label="Checkout steps" steps={STEPS} current={STEP_OF[shown]} allDone={shown === 'done'} />
      )}
      <p role="status" className="sr-only">
        {outcome(shown, handover.rental?.reference ?? null)}
      </p>
      <div ref={changedRef} tabIndex={-1} className="mb-lg empty:hidden">
        {unitsChanged !== null && handover.rental === null && (
          <Notice tone="success" title={unitsChanged.title}>
            <p>{unitsChanged.body}</p>
          </Notice>
        )}
      </div>

      {handover.rental !== null ? (
        <HandedOver rental={handover.rental} headingRef={heading} />
      ) : phase === 'failed' ? (
        <ErrorState what="this booking" error={checkout.error} onRetry={() => void checkout.refetch()} />
      ) : data === undefined ? (
        <LoadingState label="Loading the booking" shape="detail" count={2} />
      ) : data.rentalId !== null ? (
        <AlreadyOut checkout={data} />
      ) : !data.canCheckOut ? (
        <>
          <CannotCheckOut checkout={data} />
          {data.unitsShort > 0 && (
            <UnitsShort checkout={data} onReallocated={(answered) => setUnitsChanged(reallocatedWords(answered))} />
          )}
          {owner && (
            <SetAsideUnits checkout={data} onReleased={(unit) => setUnitsChanged(releasedWords(unit, data.reference))} />
          )}
        </>
      ) : (
        <CheckoutForm
          key={data.reservationId}
          checkout={data}
          stage={stage}
          onStage={setStage}
          handover={handover}
          headingRef={heading}
          onReload={() => void checkout.refetch()}
          unitAction={
            owner
              ? (unit) => (
                  <ReleaseUnit
                    checkout={data}
                    unit={unit}
                    onReleased={(released) => setUnitsChanged(releasedWords(released, data.reference))}
                  />
                )
              : undefined
          }
        />
      )}
    </>
  )
}
