/**
 * The last two panels of the SC-14 checkout wizard, the confirmation shown
 * once the equipment has gone out, and the recovery screen for an address
 * that does not match a hire.
 *
 * The deposit is simulated and the panel says so plainly. A prototype that
 * showed a card being charged would be claiming something that is not true.
 */

import { Link } from 'react-router-dom'
import { Banknote, CreditCard, Landmark, PackageCheck } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { money } from '../../shared/format'
import { rentals } from '../../shared/fixtures'
import { Card, Field, Notice, PageHeader } from '../../shared/ui'
import type { CheckoutRow, DepositMethod, ItemDraft } from './SC14-checkout-model'
import { CONDITION_LABEL } from './SC14-checkout-model'
import { CheckRow } from './SC14-CheckoutSteps'

/** Shown when the address carries a reference no hire matches. */
export function HireNotFound({ searched }: { searched: string }) {
  const openHires = rentals.filter((rental) => rental.status !== 'SETTLED')
  return (
    <>
      <PageHeader
        screenId="SC-14"
        title="Checkout and deposit"
        subtitle="We could not find that hire."
      />
      <Notice tone="error" title={`No hire matches "${searched}"`}>
        The reference in the address does not match a hire on the system. Check
        it against the paperwork, or pick one of the open hires below.
      </Notice>
      <Card title="Open hires" className="mt-md">
        <ul className="flex flex-col gap-sm">
          {openHires.map((hire) => (
            <li key={hire.id}>
              <Link
                to={`/counter/checkout/${hire.id}`}
                className="btn-secondary w-full justify-start font-mono"
              >
                {hire.reference}
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </>
  )
}

const DEPOSIT_METHODS: {
  value: DepositMethod
  label: string
  detail: string
  Icon: LucideIcon
}[] = [
  { value: 'CARD_HOLD', label: 'Card hold', detail: 'Held on the card, released at return', Icon: CreditCard },
  { value: 'CASH', label: 'Cash at the counter', detail: 'Counted into the till and receipted', Icon: Banknote },
  { value: 'EFT', label: 'EFT already received', detail: 'Paid in before collection', Icon: Landmark },
]

export function DepositStep({
  amount,
  method,
  onMethod,
  reference,
  onReference,
}: {
  amount: number
  method: DepositMethod | null
  onMethod: (next: DepositMethod) => void
  reference: string
  onReference: (next: string) => void
}) {
  return (
    <div className="flex flex-col gap-md">
      <div className="rounded bg-muted p-md">
        <p className="text-sm text-slate-soft">Refundable deposit to take now</p>
        <p className="tabular mt-xs text-3xl font-semibold text-ink">
          {money(amount)}
        </p>
      </div>

      <Notice tone="info" title="No money moves in this prototype">
        The deposit is simulated. Nothing is authorised on a card and nothing
        reaches a bank. The amount and the method are recorded so the return
        inspection has something real to settle against.
      </Notice>

      <fieldset className="min-w-0">
        <legend className="field-label">How the deposit is being taken</legend>
        <div className="mt-xs grid gap-sm sm:grid-cols-3">
          {DEPOSIT_METHODS.map(({ value, label, detail, Icon }) => {
            const active = method === value
            return (
              <label
                key={value}
                htmlFor={`dep-${value}`}
                className={`flex min-h-[2.75rem] cursor-pointer items-start gap-sm rounded border p-sm transition-colors duration-200 ${
                  active ? 'border-accent bg-accent-wash' : 'border-line hover:bg-muted'
                }`}
              >
                <input
                  id={`dep-${value}`}
                  type="radio"
                  name="deposit-method"
                  value={value}
                  checked={active}
                  onChange={() => onMethod(value)}
                  className="mt-xs h-5 w-5 shrink-0 cursor-pointer accent-accent"
                />
                <span className="min-w-0">
                  <span className="flex items-center gap-xs text-sm font-medium text-ink">
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {label}
                  </span>
                  <span className="mt-xs block text-sm text-slate-soft">{detail}</span>
                </span>
              </label>
            )
          })}
        </div>
      </fieldset>

      <Field
        label="Receipt or authorisation reference"
        htmlFor="deposit-reference"
        help="Whatever you would write on the paper slip. Any short reference will do."
      >
        <input
          id="deposit-reference"
          type="text"
          className="field-input"
          value={reference}
          onChange={(e) => onReference(e.target.value)}
          placeholder="AUTH-4471"
        />
      </Field>
    </div>
  )
}

export function AgreementStep({
  accepted,
  onAccepted,
  signedName,
  onSignedName,
  customerName,
}: {
  accepted: boolean
  onAccepted: (next: boolean) => void
  signedName: string
  onSignedName: (next: string) => void
  customerName: string
}) {
  return (
    <div className="flex flex-col gap-md">
      <div className="max-h-56 overflow-y-auto rounded border border-line bg-muted p-md text-sm text-slate-soft">
        <h3 className="text-sm font-semibold text-ink">Hire agreement, short form</h3>
        <p className="mt-sm">
          The hirer takes the equipment listed on this hire in the condition
          recorded at collection, and returns it in the same condition, fair
          wear and tear excepted.
        </p>
        <p className="mt-sm">
          Late return is charged at the daily late fee shown against each model,
          per unit, per day, from the day after the due date.
        </p>
        <p className="mt-sm">
          Damage beyond fair wear and tear is charged at the cost of repair, up
          to the replacement value of the unit. The deposit is held against late
          fees and damage, and the balance is released at the return inspection.
        </p>
        <p className="mt-sm">
          Petrol equipment goes out with a full tank and comes back full, or is
          refuelled at cost.
        </p>
      </div>

      <CheckRow
        id="agreement-accepted"
        checked={accepted}
        onChange={onAccepted}
        title="The customer has read the agreement and accepts it"
        detail="Read the late fee and damage clauses out loud before ticking this."
      />

      <Field
        label="Signed at the counter by"
        htmlFor="signed-name"
        help={`Type the name of whoever is collecting. On file: ${customerName}.`}
      >
        <input
          id="signed-name"
          type="text"
          className="field-input"
          value={signedName}
          onChange={(e) => onSignedName(e.target.value)}
          placeholder={customerName}
        />
      </Field>
    </div>
  )
}

export function ReleaseConfirmation({
  reference,
  rows,
  draft,
  deposit,
  signedName,
}: {
  reference: string
  rows: CheckoutRow[]
  draft: Record<string, ItemDraft>
  deposit: number
  signedName: string
}) {
  return (
    <>
      <PageHeader
        screenId="SC-14"
        title="Checkout and deposit"
        subtitle={`${reference} is out. Hand over the paperwork and send them on their way.`}
      />
      <Notice tone="success" title="Equipment released">
        Signed for by {signedName}. {money(deposit)} recorded as held. No card
        was charged, this is a simulated deposit.
      </Notice>
      <Card title="What was recorded" className="mt-md">
        <ul className="flex flex-col gap-md">
          {rows.map((row) => (
            <li key={row.itemId} className="flex items-start gap-sm">
              <PackageCheck
                className="mt-xs h-5 w-5 shrink-0 text-status-available"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="font-mono text-sm font-medium text-ink">{row.tag}</p>
                <p className="text-sm text-slate-soft">
                  Out at {CONDITION_LABEL[draft[row.itemId].conditionOut]}
                  {row.hasMeter && `, ${draft[row.itemId].meter} hours on the meter`}
                  {draft[row.itemId].note && `. ${draft[row.itemId].note}`}
                </p>
              </div>
            </li>
          ))}
        </ul>
        <div className="mt-lg flex flex-wrap gap-sm border-t border-line pt-md">
          <Link to="/counter" className="btn-primary px-md">
            Back to today
          </Link>
          <Link to="/counter/locator" className="btn-secondary px-md">
            Find another unit
          </Link>
        </div>
      </Card>
    </>
  )
}
