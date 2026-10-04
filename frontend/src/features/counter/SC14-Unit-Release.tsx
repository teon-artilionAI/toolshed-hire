/**
 * The owner's release of a unit a booking holds, on SC-14.
 *
 * Each unit of the checkout carries the key of its allocation, so the release
 * is offered on each one, to a signed in administrator and to nobody else. It
 * asks first. It names the unit, says it goes back on the shelf and that the
 * booking is then short a unit until it is reallocated, and asks for the
 * reason, which the server keeps in the audit trail. Only then does one button
 * post the release.
 *
 * The answer is not read. The checkout of the booking is read again, and shows
 * the units and the shortfall as the server now has them. A 409, a unit that
 * is already out or an allocation no longer active, and a 403 show the
 * server's sentence. A refused reason shows its message under the box.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Unlink } from 'lucide-react'
import type { CheckoutUnit, ReservationCheckout } from '../../shared/api/contract'
import { MAX_REASON_LENGTH, releaseAllocation } from '../../shared/api/corrections'
import { ErrorState } from '../../shared/async-states'
import { Card, Notice } from '../../shared/ui'
import { REASON_HELP, reasonProblem } from './correction-model'
import { TextInput } from './counter-fields'
import { CONDITION_GRADE_LABEL } from './counter-labels'
import { useAllocationWrite } from './use-allocation-write'

export function ReleaseUnit({
  checkout,
  unit,
  onReleased,
}: {
  checkout: ReservationCheckout
  unit: CheckoutUnit
  /** Called once the server has released the unit. */
  onReleased: (unit: CheckoutUnit) => void
}) {
  const write = useAllocationWrite<void>(unit.allocationId, 'release')
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const askRef = useRef<HTMLButtonElement>(null)
  const reasonRef = useRef<HTMLInputElement>(null)
  const askedBefore = useRef(asking)
  const failure = write.failure
  const serverProblem = failure?.kind === 'refused' ? (failure.fields.reason ?? failure.detail) : null
  const id = `release-${unit.allocationId}`

  // Opening the question puts the cursor in the reason box. Closing it puts
  // focus back on the button that opened it.
  useEffect(() => {
    if (askedBefore.current === asking) return
    askedBefore.current = asking
    if (asking) reasonRef.current?.focus()
    else askRef.current?.focus()
  }, [asking])

  if (!asking) {
    return (
      <button ref={askRef} type="button" className="btn-secondary mt-md px-md" onClick={() => setAsking(true)}>
        <Unlink className="h-4 w-4 shrink-0" aria-hidden="true" />
        Release this unit <span className="sr-only">{unit.assetTag}</span>
      </button>
    )
  }

  function close() {
    write.clearFailure()
    setProblem(null)
    setAsking(false)
  }

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = reasonProblem(reason)
    setProblem(found)
    if (found !== null) {
      reasonRef.current?.focus()
      return
    }
    const given = reason.trim()
    write.send(
      () => releaseAllocation(unit.allocationId, given),
      () => onReleased(unit),
    )
  }

  return (
    <form noValidate onSubmit={send} aria-labelledby={`${id}-heading`} className="mt-md rounded-lg border-2 border-ink p-md">
      <h4 id={`${id}-heading`} className="text-base font-semibold text-ink">
        Release {unit.assetTag} from {checkout.reference}?
      </h4>
      <p id={`${id}-consequence`} className="mt-xs break-words text-sm text-ink">
        {unit.assetTag} goes back on the shelf for anyone to book. {checkout.reference} is then short a unit until it
        is reallocated, and it cannot go out until it is.
      </p>
      <div className="mt-md">
        <TextInput
          id={`${id}-reason`}
          label="Why"
          help={REASON_HELP}
          value={reason}
          onChange={setReason}
          error={problem ?? serverProblem ?? undefined}
          disabled={write.pending}
          maxLength={MAX_REASON_LENGTH}
          autoComplete="off"
          inputRef={reasonRef}
        />
      </div>
      {failure !== null && failure.kind !== 'fault' && failure.kind !== 'refused' && (
        <div className="mt-md">
          <Notice tone="error" title={`${unit.assetTag} was not released`}>
            <p>{failure.detail}</p>
          </Notice>
        </div>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading={`We could not release ${unit.assetTag}`} error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button type="submit" className="btn-danger px-md" disabled={write.pending} aria-describedby={`${id}-consequence`}>
          {write.pending ? 'Releasing it' : 'Yes, release it'}
        </button>
        <button type="button" className="btn-secondary px-md" disabled={write.pending} onClick={close}>
          Keep it on the booking
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? 'Releasing the unit, please wait.' : ''}
      </p>
    </form>
  )
}

/**
 * The units a booking holds, for the owner, when the booking cannot go out
 * now and so the handover form with its units is not on the screen.
 */
export function SetAsideUnits({
  checkout,
  onReleased,
}: {
  checkout: ReservationCheckout
  onReleased: (unit: CheckoutUnit) => void
}) {
  if (checkout.units.length === 0) return null
  return (
    <Card title="Units set aside for this booking" className="mt-lg">
      <ul className="flex flex-col gap-md">
        {checkout.units.map((unit) => (
          <li key={unit.allocationId} className="min-w-0 rounded-lg border border-line p-md">
            <p className="font-mono text-sm font-semibold text-ink">{unit.assetTag}</p>
            <p className="mt-xs break-words text-sm text-slate-soft">
              {unit.modelName}. Its grade now is {CONDITION_GRADE_LABEL[unit.conditionGrade]}.
            </p>
            <ReleaseUnit checkout={checkout} unit={unit} onReleased={onReleased} />
          </li>
        ))}
      </ul>
    </Card>
  )
}
