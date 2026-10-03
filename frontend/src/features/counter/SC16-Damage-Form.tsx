/**
 * Filing a damage report on SC-16, and the question that comes before it.
 *
 * The form is checked when "Record the damage and quarantine the unit" is
 * pressed. Every problem is listed above it and shown under its own control,
 * and nothing is sent. The chargeable decision has no default, so a form
 * without one is held back here (BR-40) and by the server. When the form is
 * right, the question takes its place and says in words what is about to
 * happen, that the unit is quarantined and cannot be booked until the report is
 * resolved, and what the customer is charged. "Yes, file the report" sends the
 * one request, and is disabled while it is in flight.
 *
 * A 422 sends the person back to the form, with each of the server's sentences
 * under the control it names. The server's refusal of an amount above the
 * replacement value lands under the amount, and names the most it will take.
 * A 409 or a 403 shows the server's sentence. Anything else is the shared error
 * state with a way to try again.
 *
 * The rules, the body and the question are in SC16-damage-model.ts.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ShieldAlert, Undo2 } from 'lucide-react'
import type { DamageReport, LocatedUnit, Money } from '../../shared/api/contract'
import { fileDamageReport } from '../../shared/api/damage-reports'
import { ErrorState } from '../../shared/async-states'
import { money } from '../../shared/format'
import { Notice } from '../../shared/ui'
import { ProblemList, TextArea, TextInput } from './counter-fields'
import { FAIR_WEAR_IS_NOT_CHARGED, SEVERITY_OPTIONS, chargeAnswerOf, chargeOptions } from './SC16-damage-choices'
import {
  DAMAGE_CONTROL_ID,
  EMPTY_DAMAGE_DRAFT,
  asksForRecovery,
  damageSentences,
  serverDamageErrors,
  toDamageRequest,
  validateDamage,
} from './SC16-damage-model'
import type { DamageControl, DamageDraft, DamageErrors } from './SC16-damage-model'
import { ChoiceGroup } from './SC16-DamageFields'
import { useDamageWrite } from './use-damage-write'

type Stage = 'filling' | 'asking'

const NO_ERRORS: DamageErrors = {}

/** The controls in the order the form shows them, which is the order its
 *  problems are listed in. */
const CONTROL_ORDER: readonly DamageControl[] = ['severity', 'description', 'estimate', 'chargeable', 'recovery']

const DESCRIPTION_ROWS = 4

/** What the box for the amount to recover says under it. */
function recoveryHelp(replacementValue: Money | null): string {
  return replacementValue === null
    ? 'It may not be more than the replacement value copied onto the booking. The server checks it, and names the most it will take if this is more.'
    : `It may not be more than the replacement value of ${money(replacementValue)} copied onto the booking, less anything already charged for this unit on the hire. The server checks it.`
}

export function DamageForm({
  unit,
  rentalItemId,
  replacementValue,
  locatorHref,
  onFiled,
}: {
  unit: LocatedUnit
  /** The unit of the hire it came back on, or null for damage found outside a hire. */
  rentalItemId: string | null
  /** The replacement value the amount may not exceed, when the screen knows it. */
  replacementValue: Money | null
  /** Where Cancel goes. */
  locatorHref: string
  /** Called with the report the server answered with. */
  onFiled: (report: DamageReport) => void
}) {
  const write = useDamageWrite(unit.assetTag, 'file')
  const [draft, setDraft] = useState<DamageDraft>(EMPTY_DAMAGE_DRAFT)
  const [stage, setStage] = useState<Stage>('filling')
  const [tried, setTried] = useState(false)
  const failure = write.failure
  const recoveryShown = asksForRecovery(draft, rentalItemId)
  const shown = CONTROL_ORDER.filter((control) => control !== 'recovery' || recoveryShown)
  const server = failure?.kind === 'refused' ? serverDamageErrors(failure.fields, shown) : null
  const clientErrors = validateDamage(draft, rentalItemId)
  const errors: DamageErrors = { ...(tried ? clientErrors : NO_ERRORS), ...(server?.byControl ?? NO_ERRORS) }
  const problems = shown.flatMap((control) => {
    const message = errors[control]
    return message === undefined ? [] : [{ id: DAMAGE_CONTROL_ID[control], message }]
  })
  const leftOver = server === null ? [] : server.leftOver
  if (failure?.kind === 'refused' && problems.length === 0 && leftOver.length === 0) leftOver.push(failure.detail)

  // Only a change of stage moves focus, to the heading of the new stage.
  const heading = useRef<HTMLHeadingElement>(null)
  const stageBefore = useRef(stage)
  useEffect(() => {
    if (stageBefore.current === stage) return
    stageBefore.current = stage
    heading.current?.focus()
  }, [stage])

  // A refusal about a field sends the person back to the form, where the
  // message is under the control it names.
  const refusedAField = failure?.kind === 'refused'
  useEffect(() => {
    if (stage === 'asking' && refusedAField) setStage('filling')
  }, [stage, refusedAField])

  function patch(change: Partial<DamageDraft>) {
    setDraft((current) => ({ ...current, ...change }))
  }

  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTried(true)
    write.clearFailure()
    if (Object.keys(clientErrors).length > 0) return
    setStage('asking')
  }

  function send() {
    const body = toDamageRequest(unit.assetTag, rentalItemId, draft)
    write.send(() => fileDamageReport(body), onFiled)
  }

  if (stage === 'asking') {
    return (
      <section className="card border-2 border-ink p-lg" aria-labelledby="damage-question">
        <h2 id="damage-question" ref={heading} tabIndex={-1} className="text-lg font-semibold text-ink">
          File this damage report for {unit.assetTag}?
        </h2>
        <div className="mt-sm flex flex-col gap-xs text-sm text-ink">
          {damageSentences(unit, rentalItemId, draft).map((sentence) => (
            <p key={sentence}>{sentence}</p>
          ))}
        </div>
        <div className="mt-lg flex flex-wrap gap-sm">
          <button type="button" className="btn-primary px-lg" disabled={write.pending} onClick={send}>
            <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
            {write.pending ? 'Filing the report' : 'Yes, file the report'}
          </button>
          <button
            type="button"
            className="btn-secondary px-md"
            disabled={write.pending}
            onClick={() => {
              write.clearFailure()
              setStage('filling')
            }}
          >
            <Undo2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            Go back and change something
          </button>
        </div>
        <p role="status" className="sr-only">
          {write.pending ? 'Filing the report, please wait.' : ''}
        </p>
        {failure !== null && failure.kind === 'fault' && (
          <div className="mt-md">
            <ErrorState heading="We could not file the report" error={failure.error} onRetry={send} />
          </div>
        )}
        {failure !== null && failure.kind !== 'fault' && failure.kind !== 'refused' && (
          <div className="mt-md">
            <Notice tone="error" title="The report was not filed">
              <p>{failure.detail}</p>
            </Notice>
          </div>
        )}
      </section>
    )
  }

  const count = problems.length + leftOver.length
  return (
    <form noValidate onSubmit={ask} aria-labelledby="damage-form-heading" className="card p-lg">
      <h2 id="damage-form-heading" ref={heading} tabIndex={-1} className="mb-md text-lg font-semibold text-ink">
        What happened
      </h2>
      {count > 0 && (
        <div className="mb-lg">
          <Notice tone="error" title={`Nothing has been filed yet. ${count} ${count === 1 ? 'answer needs' : 'answers need'} fixing.`}>
            <ProblemList problems={problems} />
            {leftOver.length > 0 && (
              <ul className="mt-xs list-disc pl-lg">
                {leftOver.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
          </Notice>
        </div>
      )}

      <div className="flex flex-col gap-lg">
        <ChoiceGroup
          id={DAMAGE_CONTROL_ID.severity}
          legend="How bad is it"
          options={SEVERITY_OPTIONS}
          value={draft.severity}
          onChange={(severity) => patch({ severity })}
          error={errors.severity}
          columns={3}
        />
        <TextArea
          id={DAMAGE_CONTROL_ID.description}
          label="Describe the damage"
          help="What is broken, how it happened if you know, and whether the unit still runs."
          rows={DESCRIPTION_ROWS}
          value={draft.description}
          onChange={(description) => patch({ description })}
          error={errors.description}
        />
        <TextInput
          id={DAMAGE_CONTROL_ID.estimate}
          label="Estimated repair cost, in rand"
          help="Your best guess when the workshop has not quoted yet, for example 450.00."
          inputMode="decimal"
          autoComplete="off"
          value={draft.estimate}
          onChange={(estimate) => patch({ estimate })}
          error={errors.estimate}
        />
        <ChoiceGroup
          id={DAMAGE_CONTROL_ID.chargeable}
          legend="Is the customer charged for this damage?"
          help={FAIR_WEAR_IS_NOT_CHARGED}
          options={chargeOptions(rentalItemId !== null)}
          value={chargeAnswerOf(draft.chargeable)}
          onChange={(answer) => patch({ chargeable: answer === 'charge' })}
          error={errors.chargeable}
          columns={2}
        />
        {recoveryShown && (
          <TextInput
            id={DAMAGE_CONTROL_ID.recovery}
            label="Amount to recover from the customer, in rand, including VAT"
            help={recoveryHelp(replacementValue)}
            inputMode="decimal"
            autoComplete="off"
            value={draft.recovery}
            onChange={(recovery) => patch({ recovery })}
            error={errors.recovery}
          />
        )}
      </div>

      <div className="mt-lg flex flex-wrap gap-sm border-t border-line pt-md">
        <button type="submit" className="btn-primary px-md">
          <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          Record the damage and quarantine the unit
        </button>
        <Link to={locatorHref} className="btn-secondary px-md">
          Cancel
        </Link>
      </div>
    </form>
  )
}
