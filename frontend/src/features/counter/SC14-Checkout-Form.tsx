/**
 * The handover form of SC-14, and the question that comes after it.
 *
 * The form is checked when "Check out the equipment" is pressed. Every problem
 * is listed above it and shown under its own control, and nothing is sent.
 * When the form is right, the question takes its place and says in words what
 * is about to happen. "Yes, hand it over" sends the one request, and is
 * disabled while it is in flight.
 *
 * A 422 sends the person back to the form, with each of the server's sentences
 * under the control it names. A 409 or a 403 shows the server's sentence and
 * offers to read the booking again, because something about it has changed.
 * Anything else is the shared error state with a way to try again.
 *
 * The rules and the body are in checkout-form.ts.
 */

import { useEffect, useState } from 'react'
import type { ReactNode, RefObject } from 'react'
import { PackageCheck, RotateCw } from 'lucide-react'
import type { CheckoutUnit, ReservationCheckout } from '../../shared/api/contract'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { draftFor, serverErrorsByControl, toCheckoutRequest, validateCheckout } from './checkout-form'
import type { CheckoutDraft, CheckoutErrors, UnitDraft } from './checkout-form'
import { ProblemList } from './counter-fields'
import { StepHeading } from './counter-steps'
import { UnitFields } from './SC14-CheckoutSteps'
import { ConfirmHandover, DepositAndAgreement } from './SC14-CheckoutFinish'
import type { Handover } from './use-handover'

/** Filling the form in, or answering the question that comes after it. */
export type CheckoutStage = 'filling' | 'asking'

const NO_ERRORS: CheckoutErrors = {}

const RELOAD_LABEL = 'Load the booking again'

export function CheckoutForm({
  checkout,
  stage,
  onStage,
  handover,
  headingRef,
  onReload,
  unitAction,
}: {
  checkout: ReservationCheckout
  stage: CheckoutStage
  onStage: (stage: CheckoutStage) => void
  handover: Handover
  headingRef: RefObject<HTMLHeadingElement | null>
  onReload: () => void
  /** What else is offered on each unit, such as the owner's release of it. */
  unitAction?: (unit: CheckoutUnit) => ReactNode
}) {
  const [draft, setDraft] = useState<CheckoutDraft>(() => draftFor(checkout))
  const [tried, setTried] = useState(false)
  const refusal = handover.failure
  const server = refusal?.kind === 'refused' ? serverErrorsByControl(refusal.fields) : null
  const clientErrors = validateCheckout(checkout, draft)
  const errors: CheckoutErrors = { ...(tried ? clientErrors : NO_ERRORS), ...(server?.byControl ?? NO_ERRORS) }
  const problems = Object.entries(errors).map(([id, message]) => ({ id, message }))
  const leftOver = server?.leftOver ?? []

  // A refusal about a field sends the person back to the form, where the
  // message is under the control it names.
  const refusedAField = refusal?.kind === 'refused'
  useEffect(() => {
    if (stage === 'asking' && refusedAField) onStage('filling')
  }, [stage, refusedAField, onStage])

  function patchUnit(allocationId: string, patch: Partial<UnitDraft>) {
    setDraft((current) => ({
      ...current,
      units: { ...current.units, [allocationId]: { ...current.units[allocationId], ...patch } },
    }))
  }

  function ask() {
    setTried(true)
    handover.clearFailure()
    if (Object.keys(clientErrors).length > 0) return
    onStage('asking')
  }

  function send() {
    handover.send(toCheckoutRequest(checkout, draft))
  }

  if (stage === 'asking') {
    return (
      <>
        <ConfirmHandover
          checkout={checkout}
          pending={handover.pending}
          headingRef={headingRef}
          onConfirm={send}
          onBack={() => {
            handover.clearFailure()
            onStage('filling')
          }}
        />
        <p role="status" className="sr-only">
          {handover.pending ? 'Handing the equipment over, please wait.' : ''}
        </p>
        {refusal !== null && refusal.kind === 'fault' && (
          <div className="mt-md">
            <ErrorState heading="We could not record the handover" error={refusal.error} onRetry={send}>
              <button type="button" className="btn-ghost px-md" onClick={onReload}>
                {RELOAD_LABEL}
              </button>
            </ErrorState>
          </div>
        )}
        {refusal !== null && refusal.kind !== 'fault' && refusal.kind !== 'refused' && (
          <div className="mt-md">
            <Notice tone="error" title="The equipment cannot go out">
              <p>{refusal.detail}</p>
              <button type="button" className="btn-secondary mt-sm px-md" onClick={onReload}>
                <RotateCw className="h-4 w-4 shrink-0" aria-hidden="true" />
                {RELOAD_LABEL}
              </button>
            </Notice>
          </div>
        )}
      </>
    )
  }

  return (
    <div className="flex flex-col gap-lg">
      <StepHeading headingRef={headingRef}>Step 1 of 3. Check each unit and take the deposit</StepHeading>
      {(problems.length > 0 || leftOver.length > 0) && (
        <Notice
          tone="error"
          title={`Nothing has gone out yet. ${Math.max(problems.length, leftOver.length)} ${
            Math.max(problems.length, leftOver.length) === 1 ? 'answer needs' : 'answers need'
          } fixing.`}
        >
          <ProblemList problems={problems} />
          {leftOver.length > 0 && (
            <ul className="mt-xs list-disc pl-lg">
              {leftOver.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          )}
        </Notice>
      )}
      <section aria-label="The units going out" className="flex flex-col gap-md">
        {checkout.units.map((unit, index) => (
          <UnitFields
            key={unit.allocationId}
            unit={unit}
            index={index}
            answers={draft.units[unit.allocationId]}
            errors={errors}
            disabled={handover.pending}
            onChange={(patch) => patchUnit(unit.allocationId, patch)}
          >
            {unitAction?.(unit)}
          </UnitFields>
        ))}
      </section>
      <DepositAndAgreement
        checkout={checkout}
        signed={draft.agreementSigned}
        onSigned={(agreementSigned) => setDraft((current) => ({ ...current, agreementSigned }))}
        errors={errors}
        disabled={handover.pending}
      />
      <div>
        <button type="button" className="btn-primary px-lg" onClick={ask}>
          <PackageCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
          Check out the equipment
        </button>
      </div>
    </div>
  )
}
