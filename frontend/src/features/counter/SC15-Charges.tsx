/**
 * Every charge on a hire, on SC-15, and the owner's corrections of them.
 *
 * The charges are listed in the order the server sent them, each with what it
 * is for, the server's sentence about it, its amount in words that say which
 * way it runs, where it stands and when it was raised. A reversal says which
 * charge it reverses, a charge with a reversal says so, and a charge the owner
 * waived, reversed or added shows the reason they gave.
 *
 * For a signed in administrator and nobody else, each charge offers what the
 * server allows for where it stands. "Waive" on a pending charge, and
 * "Reverse" on a settled one that no other charge on the hire reverses yet.
 * The server never reverses a movement of the deposit, because it works the
 * deposit out again after every correction, and never reverses a reversal, so
 * neither is offered. The server sends no flag for any of this, so the offer
 * follows the type, the status and `reversesChargeId` it sends, and its 409 is
 * the last word. "Adjust the hire" adds a charge of the owner's own amount.
 * Counter staff see the sentence that only the owner can waive a charge.
 */

import { useState } from 'react'
import { Scale, Undo2 } from 'lucide-react'
import type { ChargeType, Rental, RentalCharge } from '../../shared/api/contract'
import { branchDateTime } from '../../shared/today'
import { Card } from '../../shared/ui'
import { CHARGE_NOUN, CHARGE_STATUS_LABEL, CHARGE_TYPE_LABEL, amountWords } from './counter-labels'
import { ChargeCorrection } from './SC15-Charge-Correction'
import type { ChargeCorrectionKind } from './SC15-Charge-Correction'
import { HireAdjustment } from './SC15-Hire-Adjustment'
import { ONLY_THE_OWNER_CAN_WAIVE } from './SC15-ItemInspection'
import type { CorrectionKind } from './use-rental-write'

/** What a correction did, for the notice at the top of the screen. */
export interface Corrected {
  kind: CorrectionKind
  rental: Rental
  /** The charge it was made to, or null for an adjustment of the hire. */
  charge: RentalCharge | null
}

/** The charges that move the deposit, which the server refuses to reverse. */
const DEPOSIT_MOVEMENTS: readonly ChargeType[] = ['DEPOSIT_HOLD', 'DEPOSIT_RELEASE', 'DEPOSIT_FORFEIT']

/** Whether the server would take a reversal of a settled charge. */
function mayBeReversed(charge: RentalCharge, charges: readonly RentalCharge[]): boolean {
  return (
    !DEPOSIT_MOVEMENTS.includes(charge.type) &&
    charge.reversesChargeId === null &&
    !charges.some((other) => other.reversesChargeId === charge.id)
  )
}

/** Which correction the server allows for a charge where it stands, if any. */
function correctionFor(charge: RentalCharge, charges: readonly RentalCharge[]): ChargeCorrectionKind | null {
  if (charge.status === 'PENDING') return 'waiver'
  if (charge.status === 'SETTLED' && mayBeReversed(charge, charges)) return 'reversal'
  return null
}

/** What a reversal reverses, in words. */
function reversesWords(charge: RentalCharge, charges: readonly RentalCharge[]): string {
  const original = charges.find((other) => other.id === charge.reversesChargeId)
  if (original === undefined) return 'This reverses an earlier charge on this hire.'
  return `This reverses the ${CHARGE_NOUN[original.type]} of ${amountWords(original.amountIncVat)} raised ${branchDateTime(original.raisedAt)}.`
}

function ChargeEntry({
  rental,
  charge,
  ownerSignedIn,
  onCorrected,
}: {
  rental: Rental
  charge: RentalCharge
  ownerSignedIn: boolean
  onCorrected: (corrected: Corrected) => void
}) {
  const [correcting, setCorrecting] = useState(false)
  const offer = correctionFor(charge, rental.charges)
  const reversed = rental.charges.some((other) => other.reversesChargeId === charge.id)
  const titleId = `charge-${charge.id}`
  return (
    <article aria-labelledby={titleId} className="min-w-0 rounded-lg border border-line p-md">
      <div className="flex flex-wrap items-baseline justify-between gap-x-md gap-y-xs">
        <h3 id={titleId} className="text-base font-semibold text-ink">
          {CHARGE_TYPE_LABEL[charge.type]}
        </h3>
        <p className="tabular font-mono text-sm text-ink">{amountWords(charge.amountIncVat)}</p>
      </div>
      <p className="mt-xs break-words text-sm text-ink">{charge.description}</p>
      <p className="mt-xs text-sm text-slate-soft">
        {CHARGE_STATUS_LABEL[charge.status]}. Raised {branchDateTime(charge.raisedAt)}.
      </p>
      {charge.reversesChargeId !== null && (
        <p className="mt-xs text-sm text-ink">{reversesWords(charge, rental.charges)}</p>
      )}
      {reversed && <p className="mt-xs text-sm text-ink">A later charge on this hire reverses this one.</p>}
      {charge.reason !== null && (
        <dl className="mt-xs flex flex-wrap gap-x-sm text-sm">
          <dt className="text-slate-soft">The owner&apos;s reason</dt>
          <dd className="min-w-0 break-words text-ink">{charge.reason}</dd>
        </dl>
      )}
      {ownerSignedIn && offer !== null && !correcting && (
        <button type="button" className="btn-secondary mt-sm px-md" onClick={() => setCorrecting(true)}>
          <Undo2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          {offer === 'waiver' ? 'Waive' : 'Reverse'}{' '}
          <span className="sr-only">
            the {CHARGE_NOUN[charge.type]} of {amountWords(charge.amountIncVat)}
          </span>
        </button>
      )}
      {ownerSignedIn && offer !== null && correcting && (
        <ChargeCorrection
          rental={rental}
          charge={charge}
          kind={offer}
          onCorrected={(answered) => {
            setCorrecting(false)
            onCorrected({ kind: offer, rental: answered, charge })
          }}
          onCancel={() => setCorrecting(false)}
        />
      )}
    </article>
  )
}

export function RentalCharges({
  rental,
  ownerSignedIn,
  onCorrected,
}: {
  rental: Rental
  /** True only for a signed in administrator. */
  ownerSignedIn: boolean
  onCorrected: (corrected: Corrected) => void
}) {
  const [adjusting, setAdjusting] = useState(false)
  return (
    <Card title="Charges on this hire">
      {rental.charges.length === 0 ? (
        <p className="text-sm text-slate-soft">No charge has been raised on this hire.</p>
      ) : (
        <ul className="flex flex-col gap-sm" aria-label={`Charges on ${rental.reference}, in the order they were raised`}>
          {rental.charges.map((charge) => (
            <li key={charge.id}>
              <ChargeEntry rental={rental} charge={charge} ownerSignedIn={ownerSignedIn} onCorrected={onCorrected} />
            </li>
          ))}
        </ul>
      )}
      {!ownerSignedIn && (
        <p className="mt-md text-sm text-ink">
          {ONLY_THE_OWNER_CAN_WAIVE} Tell them when a charge looks wrong, and they can waive it, reverse it or
          adjust the hire.
        </p>
      )}
      {ownerSignedIn && !adjusting && (
        <div className="mt-md border-t border-line pt-md">
          <button type="button" className="btn-secondary px-md" onClick={() => setAdjusting(true)}>
            <Scale className="h-4 w-4 shrink-0" aria-hidden="true" />
            Adjust the hire
          </button>
          <p className="field-help">Adds a charge of your own amount, including VAT, to the hire.</p>
        </div>
      )}
      {ownerSignedIn && adjusting && (
        <HireAdjustment
          rental={rental}
          onAdjusted={(answered) => {
            setAdjusting(false)
            onCorrected({ kind: 'adjustment', rental: answered, charge: null })
          }}
          onCancel={() => setAdjusting(false)}
        />
      )}
    </Card>
  )
}
