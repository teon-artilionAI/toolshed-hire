/**
 * The hire basket itself, on SC-04, before anything has been asked of the
 * server.
 *
 * The person checks the dates, the branch and how many of each tool, and can
 * change any of them. A change is a change to the basket, and it is kept for
 * the tab straight away.
 *
 * There is no price here. Pressing the button creates the reservation as a
 * draft, and the server's answer to that is the price. Who may press it
 * depends on who is asking. A visitor is sent to sign in and brought back. A
 * customer whose account is on hold is shown the server's reason and no
 * button. Staff book for a customer at the counter and not here.
 *
 * What the API refuses about the dates, the branch or a line is shown under
 * the field it is about.
 */

import type { RefObject } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ClipboardCheck, Loader2 } from 'lucide-react'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { removeFromBasket, setBasketQuantity, setBasketTerms } from '../../shared/basket-store'
import type { Basket } from '../../shared/basket-store'
import { signInAddress } from '../../shared/screen-access'
import { todayInBranchTime } from '../../shared/today'
import { Card, Notice } from '../../shared/ui'
import BasketLine from './basket-line'
import { AccountOnHoldNotice, BookingRefusalNotice } from './booking-refusal-notice'
import { StepHeading } from './booking-steps'
import { ANY_BRANCH, BranchSelect, PeriodFields } from './catalogue-ui'
import { describePeriod } from './hire-period'
import type { Booking } from './use-booking'

/** The address of this screen, where a visitor is brought back to. */
const BASKET_PATH = '/basket'

const NO_FIELD_ERRORS: FieldErrors = {}

/** Who is looking at the basket, which decides what the button offers. */
export type BasketAudience = 'visitor' | 'customer' | 'staff'

/** The message the API sent about one line, by its place in the request. */
function lineError(fields: FieldErrors, index: number): string | undefined {
  return fields[`lines.${index}.quantity`] ?? fields[`lines.${index}.modelSlug`]
}

export default function BasketStep({
  basket,
  audience,
  booking,
  headingRef,
}: {
  basket: Basket
  audience: BasketAudience
  booking: Booking
  headingRef: RefObject<HTMLHeadingElement | null>
}) {
  const branches = useQuery(catalogueQueries.branches())
  const busy = booking.pending !== null
  const refusal = booking.failure?.action === 'review' ? booking.failure.refusal : null
  const fields = refusal?.kind === 'refused' ? refusal.fields : NO_FIELD_ERRORS
  const shownFields = [
    'from',
    'to',
    'branchCode',
    ...basket.lines.flatMap((_, index) => [`lines.${index}.quantity`, `lines.${index}.modelSlug`]),
  ]
  const periodLabel = describePeriod(basket.from, basket.to)
  const answerable = basket.from !== '' && basket.to !== '' && basket.branchCode !== ''

  return (
    <>
      <StepHeading headingRef={headingRef}>Check your basket</StepHeading>
      <div className="grid gap-lg lg:grid-cols-5">
        <div className="flex min-w-0 flex-col gap-lg lg:col-span-3">
          <Card title="When and where">
            <fieldset className="grid gap-md sm:grid-cols-3" disabled={busy}>
              <legend className="sr-only">The dates and the branch for the whole hire</legend>
              <PeriodFields
                idPrefix="basket"
                startIso={basket.from}
                endIso={basket.to}
                minIso={todayInBranchTime()}
                onChangeStart={(from) => setBasketTerms({ from })}
                onChangeEnd={(to) => setBasketTerms({ to })}
                startError={basket.from ? fields.from : 'Choose a collection date.'}
                endError={basket.to ? fields.to : 'Choose a return date.'}
              />
              <BranchSelect
                id="basket-branch"
                branches={branches.data?.items ?? []}
                value={basket.branchCode}
                onChange={(value) => {
                  if (value !== ANY_BRANCH) setBasketTerms({ branchCode: value })
                }}
                error={fields.branchCode}
              />
            </fieldset>
            <p className="mt-md text-sm text-slate-soft">
              {periodLabel ? `${periodLabel}. ` : ''}One hire has one set of dates and one
              collection branch, so these apply to everything in the basket.
            </p>
          </Card>

          <Card title="What you are hiring">
            <ul className="flex flex-col gap-lg">
              {basket.lines.map((line, index) => (
                <BasketLine
                  key={line.modelSlug}
                  line={line}
                  terms={basket}
                  error={lineError(fields, index)}
                  disabled={busy}
                  onChangeQuantity={setBasketQuantity}
                  onRemove={removeFromBasket}
                />
              ))}
            </ul>
          </Card>
        </div>

        <div className="min-w-0 lg:col-span-2 lg:sticky lg:top-24 lg:self-start">
          <Card title="Review and book">
            <p className="text-sm text-slate-soft">
              The next step prices this basket and shows you every figure. Nothing is held and
              nothing is charged until you say so.
            </p>

            {refusal && (
              <div className="mt-md">
                <BookingRefusalNotice
                  refusal={refusal}
                  conflictTitle="We could not price this basket"
                  faultHeading="We could not price your basket"
                  otherMessages={otherFieldMessages(fields, shownFields)}
                  onRetry={booking.review}
                />
              </div>
            )}

            <div className="mt-md">
              {booking.blockedBecause !== null ? (
                <AccountOnHoldNotice because={booking.blockedBecause} />
              ) : audience === 'visitor' ? (
                <>
                  <Link to={signInAddress(BASKET_PATH)} className="btn-primary w-full">
                    Sign in to review and book
                  </Link>
                  <p className="mt-sm text-sm text-slate-soft">
                    You need an account to book. Your basket will be here when you come back.
                  </p>
                </>
              ) : audience === 'staff' ? (
                <Notice tone="info" title="Booking online is for customer accounts">
                  <p>
                    You are signed in as staff. Book for a customer from the counter, on the new
                    booking screen.
                  </p>
                </Notice>
              ) : (
                <>
                  <button
                    type="button"
                    className="btn-primary w-full"
                    disabled={busy || !answerable}
                    onClick={booking.review}
                  >
                    {booking.pending === 'review' ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
                    ) : (
                      <ClipboardCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                    )}
                    {booking.pending === 'review' ? 'Working out the cost' : 'Review and book'}
                  </button>
                  <p className="mt-sm text-center text-sm text-slate-soft">
                    You pay at the counter when you collect.
                  </p>
                </>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
