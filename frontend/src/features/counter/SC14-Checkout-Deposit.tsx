/**
 * SC-14 Checkout and Deposit.
 *
 * The counter side of handing equipment over. It is a wizard rather than one
 * long form because the five things it records happen in a fixed order at a
 * real counter: read the tags, grade the units, count the accessories, take
 * the deposit, get the agreement accepted. One long page would let somebody
 * take a deposit for a unit whose tag was never checked.
 *
 * The deposit is simulated and the screen says so. Nothing is authorised on
 * a card.
 */

import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check } from 'lucide-react'
import { assets, customers, productModels, rentals } from '../../shared/fixtures'
import { formatDate } from '../../shared/format'
import { Card, Notice, PageHeader, StatusPill } from '../../shared/ui'
import type { CheckoutRow, DepositMethod, ItemDraft } from './SC14-checkout-model'
import { accessoriesFor } from './SC14-checkout-model'
import { AccessoryStep, ConditionStep, TagStep } from './SC14-CheckoutSteps'
import {
  AgreementStep,
  DepositStep,
  HireNotFound,
  ReleaseConfirmation,
} from './SC14-CheckoutFinish'

const STEPS = [
  'Check the tags',
  'Condition and meter',
  'Accessories',
  'Deposit',
  'Agreement',
] as const

const MIN_REFERENCE_LENGTH = 3
const MIN_SIGNATURE_LENGTH = 2

export default function CheckoutAndDeposit() {
  const { rentalId } = useParams()
  const rental = rentals.find((r) => r.id === rentalId || r.reference === rentalId)

  if (!rental) return <HireNotFound searched={rentalId ?? ''} />
  return <CheckoutWizard key={rental.id} rentalKey={rental.id} />
}

function CheckoutWizard({ rentalKey }: { rentalKey: string }) {
  const rental = rentals.find((r) => r.id === rentalKey)!
  const customerName =
    customers.find((c) => c.id === rental.customerId)?.name ?? 'the customer'

  const rows = useMemo<CheckoutRow[]>(
    () =>
      rental.items.map((item) => {
        const asset = assets.find((a) => a.id === item.assetId)
        const model = productModels.find((m) => m.id === asset?.productModelId)
        return {
          itemId: item.id,
          tag: asset?.tag ?? 'Tag missing',
          modelName: model?.name ?? 'Unknown model',
          manufacturer: model?.manufacturer ?? '',
          categoryId: model?.categoryId ?? '',
          hasMeter: asset?.meterHours !== undefined,
          meterOnFile: asset?.meterHours,
          conditionOnFile: asset?.condition ?? 'B',
        }
      }),
    [rental],
  )

  const accessories = useMemo(
    () => accessoriesFor(rows.map((r) => r.categoryId)),
    [rows],
  )

  const [step, setStep] = useState(0)
  const [released, setReleased] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<Record<string, ItemDraft>>(() =>
    Object.fromEntries(
      rows.map((row) => [
        row.itemId,
        {
          tagConfirmed: false,
          conditionOut: row.conditionOnFile,
          meter: row.meterOnFile === undefined ? '' : String(row.meterOnFile),
          note: '',
        },
      ]),
    ),
  )
  const [checkedAccessories, setCheckedAccessories] = useState<Record<string, boolean>>({})
  const [method, setMethod] = useState<DepositMethod | null>(null)
  const [reference, setReference] = useState('')
  const [accepted, setAccepted] = useState(false)
  const [signedName, setSignedName] = useState('')

  function patchItem(itemId: string, patch: Partial<ItemDraft>) {
    setDraft((current) => ({ ...current, [itemId]: { ...current[itemId], ...patch } }))
    setError(null)
  }

  /** What is stopping this step from being finished, in plain words. */
  function problemWith(index: number): string | null {
    if (index === 0 && rows.some((row) => !draft[row.itemId].tagConfirmed)) {
      return 'Tick every asset tag before you carry on. If a tag does not match the paperwork, go back to the booking and reallocate the unit.'
    }
    if (index === 1) {
      const noMeter = rows.find((r) => r.hasMeter && draft[r.itemId].meter.trim() === '')
      if (noMeter) {
        return `Enter the hour meter reading for ${noMeter.tag}. The return inspection cannot work out the hours used without it.`
      }
      const damaged = rows.find((r) => draft[r.itemId].conditionOut === 'D')
      if (damaged) {
        return `${damaged.tag} is graded D, damaged. Send it to the workshop and allocate a different unit rather than releasing it.`
      }
    }
    if (index === 2 && !accessories.some((item) => checkedAccessories[item])) {
      return 'Tick at least the operating manual. If genuinely nothing goes out with the unit, put that in the condition notes instead.'
    }
    if (index === 3) {
      if (!method) return 'Choose how the deposit is being taken.'
      if (reference.trim().length < MIN_REFERENCE_LENGTH) {
        return 'Enter the receipt or authorisation reference, at least three characters, so the deposit can be traced at return.'
      }
    }
    if (index === 4) {
      if (!accepted) {
        return 'The customer has to accept the hire agreement before the equipment leaves the counter.'
      }
      if (signedName.trim().length < MIN_SIGNATURE_LENGTH) {
        return 'Type the name of whoever is signing for the equipment.'
      }
    }
    return null
  }

  function goNext() {
    const problem = problemWith(step)
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    if (step === STEPS.length - 1) setReleased(true)
    else setStep(step + 1)
  }

  if (released) {
    return (
      <ReleaseConfirmation
        reference={rental.reference}
        rows={rows}
        draft={draft}
        deposit={rental.depositHeld}
        signedName={signedName}
      />
    )
  }

  return (
    <>
      <PageHeader
        screenId="SC-14"
        title="Checkout and deposit"
        subtitle={`${rental.reference} for ${customerName}. Due back ${formatDate(rental.dueBackOn)}.`}
        actions={<StatusPill status={rental.status} />}
      />

      <ol aria-label="Checkout progress" className="mb-lg flex flex-wrap gap-sm">
        {STEPS.map((label, index) => {
          const done = index < step
          const current = index === step
          return (
            <li key={label}>
              <button
                type="button"
                disabled={index > step}
                aria-current={current ? 'step' : undefined}
                onClick={() => {
                  setStep(index)
                  setError(null)
                }}
                className={`btn px-md text-left ${
                  current
                    ? 'bg-accent font-semibold text-accent-ink'
                    : done
                      ? 'border border-line bg-surface text-ink hover:bg-muted'
                      : 'border border-line bg-muted text-slate-soft'
                }`}
              >
                {done ? (
                  <Check className="h-4 w-4 shrink-0" aria-hidden="true" />
                ) : (
                  <span className="tabular text-xs font-semibold">{index + 1}</span>
                )}
                <span>{label}</span>
                {done && <span className="sr-only">, done</span>}
              </button>
            </li>
          )
        })}
      </ol>

      <Card title={`Step ${step + 1} of ${STEPS.length}, ${STEPS[step]}`}>
        {error && (
          <div className="mb-md">
            <Notice tone="error" title="This step is not finished">
              {error}
            </Notice>
          </div>
        )}

        {step === 0 && (
          <TagStep
            rows={rows}
            draft={draft}
            onToggle={(id, next) => patchItem(id, { tagConfirmed: next })}
          />
        )}
        {step === 1 && <ConditionStep rows={rows} draft={draft} onChange={patchItem} />}
        {step === 2 && (
          <AccessoryStep
            accessories={accessories}
            checked={checkedAccessories}
            onToggle={(item, next) => {
              setCheckedAccessories((current) => ({ ...current, [item]: next }))
              setError(null)
            }}
          />
        )}
        {step === 3 && (
          <DepositStep
            amount={rental.depositHeld}
            method={method}
            onMethod={(next) => {
              setMethod(next)
              setError(null)
            }}
            reference={reference}
            onReference={(next) => {
              setReference(next)
              setError(null)
            }}
          />
        )}
        {step === 4 && (
          <AgreementStep
            accepted={accepted}
            onAccepted={(next) => {
              setAccepted(next)
              setError(null)
            }}
            signedName={signedName}
            onSignedName={(next) => {
              setSignedName(next)
              setError(null)
            }}
            customerName={customerName}
          />
        )}

        <div className="mt-lg flex flex-wrap gap-sm border-t border-line pt-md">
          <button
            type="button"
            className="btn-secondary px-md"
            disabled={step === 0}
            onClick={() => {
              setStep(Math.max(0, step - 1))
              setError(null)
            }}
          >
            <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
            Back
          </button>
          <button type="button" className="btn-primary px-md" onClick={goNext}>
            {step === STEPS.length - 1 ? 'Release the equipment' : 'Continue'}
            <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
          </button>
        </div>
      </Card>
    </>
  )
}
