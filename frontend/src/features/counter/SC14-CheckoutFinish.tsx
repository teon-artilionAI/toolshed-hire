/**
 * The end of a handover on SC-14. The deposit and the agreement, the question
 * that comes before the last button, and what is shown once the equipment is
 * out. Also the two answers that mean there is nothing to hand over. Once the
 * equipment is out, and when it was out already, the screen links to the
 * return of the hire on SC-15 by the key of the hire.
 *
 * The deposit is the server's figure and it is simulated. Nothing is
 * authorised on a card, and the screen says so.
 */

import type { RefObject } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, PackageCheck, Undo2 } from 'lucide-react'
import type { Rental, ReservationCheckout } from '../../shared/api/contract'
import { formatDate, money } from '../../shared/format'
import { Card, Notice } from '../../shared/ui'
import { AGREEMENT_ID, handoverSentence } from './checkout-form'
import type { CheckoutErrors } from './checkout-form'
import { CheckRow } from './counter-fields'
import { CONDITION_GRADE_LABEL, ID_DOCUMENT_LABEL } from './counter-labels'
import { COUNTER_HOME_PATH, CUSTOMERS_PATH, customerHref, rentalHref } from './counter-links'

/** The money to take and the agreement to sign. */
export function DepositAndAgreement({
  checkout,
  signed,
  onSigned,
  errors,
  disabled,
}: {
  checkout: ReservationCheckout
  signed: boolean
  onSigned: (signed: boolean) => void
  errors: CheckoutErrors
  disabled: boolean
}) {
  return (
    <Card title="Deposit and agreement">
      <div className="rounded bg-muted p-md">
        <p className="text-sm text-slate-soft">Deposit to take now</p>
        <p className="tabular mt-xs text-3xl font-semibold text-ink">{money(checkout.depositTotal)}</p>
        <p className="tabular mt-xs text-sm text-slate-soft">
          The hire itself comes to {money(checkout.hireTotalIncVat)} with VAT.
        </p>
      </div>
      <p className="mt-sm text-sm text-slate-soft">
        The deposit is simulated. Nothing is authorised on a card and nothing reaches a bank. The amount
        is recorded so the return has something to settle against.
      </p>
      <p className="mt-md text-sm text-ink">
        Check the identity document first. It should be a {ID_DOCUMENT_LABEL[checkout.customer.idDocumentType]}{' '}
        ending {checkout.customer.idDocumentLast4}, in the name of {checkout.customer.displayName}.
      </p>
      <div className="mt-md">
        <CheckRow id={AGREEMENT_ID} checked={signed} onChange={onSigned} error={errors[AGREEMENT_ID]} disabled={disabled}>
          The customer has read the hire agreement and signed it. Late returns are charged by the day and
          damage up to the value of the unit.
        </CheckRow>
      </div>
    </Card>
  )
}

/** The question before the last button, with what it will do written out. */
export function ConfirmHandover({
  checkout,
  pending,
  headingRef,
  onConfirm,
  onBack,
}: {
  checkout: ReservationCheckout
  pending: boolean
  headingRef: RefObject<HTMLHeadingElement | null>
  onConfirm: () => void
  onBack: () => void
}) {
  return (
    <section className="card border-2 border-ink p-lg" aria-labelledby="handover-question">
      <h2 id="handover-question" ref={headingRef} tabIndex={-1} className="text-lg font-semibold text-ink">
        Step 2 of 3. Hand the equipment over to {checkout.customer.displayName}?
      </h2>
      <p className="mt-sm text-sm text-ink">{handoverSentence(checkout)}</p>
      <div className="mt-lg flex flex-wrap gap-sm">
        <button type="button" className="btn-primary px-lg" disabled={pending} onClick={onConfirm}>
          {pending ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
          ) : (
            <PackageCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          {pending ? 'Handing the equipment over' : 'Yes, hand it over'}
        </button>
        <button type="button" className="btn-secondary px-md" disabled={pending} onClick={onBack}>
          <Undo2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          Go back and change something
        </button>
      </div>
    </section>
  )
}

/** What is shown once the server has made the hire. */
export function HandedOver({ rental, headingRef }: { rental: Rental; headingRef: RefObject<HTMLHeadingElement | null> }) {
  return (
    <section aria-labelledby="handed-over">
      <h2 id="handed-over" ref={headingRef} tabIndex={-1} className="mb-md text-lg font-semibold text-ink">
        Step 3 of 3. The equipment is out on hire {rental.reference}
      </h2>
      <Notice tone="success" title={`Hire ${rental.reference} is open`}>
        <p>
          {rental.customerName} has the equipment from {rental.branchName}. It is due back on{' '}
          {formatDate(rental.dueBackOn)}. {money(rental.depositHeld)} is recorded as the deposit held.
        </p>
      </Notice>
      <Card title="What went out" className="mt-lg">
        <ul className="flex flex-col gap-md">
          {rental.items.map((item) => (
            <li key={item.id} className="flex items-start gap-sm">
              <PackageCheck className="mt-xs h-5 w-5 shrink-0 text-status-available" aria-hidden="true" />
              <div className="min-w-0">
                <p className="font-mono text-sm font-medium text-ink">{item.assetTag ?? item.modelSlug}</p>
                <p className="text-sm text-slate-soft">
                  {item.modelName}, out at {CONDITION_GRADE_LABEL[item.conditionOut]}
                  {item.hourMeterOut !== null ? `, ${item.hourMeterOut} hours on the meter` : ''}
                  {item.accessoriesOut ? `. With ${item.accessoriesOut}` : ''}.
                </p>
              </div>
            </li>
          ))}
        </ul>
        <dl className="tabular mt-lg grid gap-xs border-t border-line pt-md text-sm">
          <div className="flex justify-between gap-md">
            <dt className="text-slate-soft">Deposit held</dt>
            <dd className="font-semibold text-ink">{money(rental.depositHeld)}</dd>
          </div>
          <div className="flex justify-between gap-md">
            <dt className="text-slate-soft">Due back on</dt>
            <dd className="font-semibold text-ink">{formatDate(rental.dueBackOn)}</dd>
          </div>
        </dl>
        <div className="mt-lg flex flex-wrap gap-sm">
          <Link to={customerHref(rental.customerProfileId)} className="btn-primary px-md">
            Back to {rental.customerName}
          </Link>
          <Link to={rentalHref(rental.id)} className="btn-secondary px-md">
            Open the hire
          </Link>
          <Link to={COUNTER_HOME_PATH} className="btn-secondary px-md">
            Back to today
          </Link>
        </div>
      </Card>
    </section>
  )
}

/** The reservation was collected before. */
export function AlreadyOut({ checkout }: { checkout: ReservationCheckout }) {
  return (
    <Notice tone="info" title={`${checkout.reference} is already out`}>
      <p>This booking has been collected, so there is nothing more to hand over.</p>
      {checkout.rentalId !== null && (
        <Link to={rentalHref(checkout.rentalId)} className="btn-secondary mt-sm px-md">
          Open the hire
        </Link>
      )}
    </Notice>
  )
}

/** The server says this cannot go out now, and says why. */
export function CannotCheckOut({ checkout }: { checkout: ReservationCheckout }) {
  return (
    <Notice tone="warn" title={`${checkout.reference} cannot go out now`}>
      <p>{checkout.refusal ?? 'The server did not say why.'}</p>
      <Link to={CUSTOMERS_PATH} className="btn-secondary mt-sm px-md">
        Find a customer
      </Link>
    </Notice>
  )
}
