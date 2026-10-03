/**
 * Step one of a counter booking on SC-13. The dates and the tools.
 *
 * The booking is collected at the branch the assistant works at, and the
 * first day may be today. The tools come from the availability search for
 * that branch, and each line says whether its quantity is free. Units are
 * chosen by the server when the booking is held, so there is no unit to pick.
 *
 * There is no price on this step. Pressing the button makes the reservation,
 * and the server's answer to that is the price. What the API refuses about
 * the dates or a line is shown under the field it is about.
 */

import { useState } from 'react'
import type { RefObject } from 'react'
import { Calculator, Loader2 } from 'lucide-react'
import type { ModelSummary } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { ErrorState } from '../../shared/async-states'
import { Card, Notice } from '../../shared/ui'
import {
  draftProblems,
  periodIsUsable,
  withModel,
  withQuantity,
  withoutModel,
} from './booking-draft'
import type { BookingDraft } from './booking-draft'
import { DateInput } from './counter-fields'
import { StepHeading } from './counter-steps'
import LineEditor from './SC13-Line-Editor'
import { ModelFinder } from './SC13-Model-Finder'
import type { CounterBooking } from './use-counter-booking'
import type { CounterBranch } from './work-branch-gate'

const NO_FIELD_ERRORS: FieldErrors = {}

const RETURN_HELP = 'The day it comes back is not charged.'

/** The message the API sent about one line, by its place in the request. */
function lineError(fields: FieldErrors, index: number): string | undefined {
  return fields[`lines.${index}.quantity`] ?? fields[`lines.${index}.modelSlug`]
}

export function BookingLinesStep({
  draft,
  onDraft,
  branch,
  today,
  booking,
  headingRef,
}: {
  draft: BookingDraft
  onDraft: (next: BookingDraft) => void
  branch: CounterBranch
  today: string
  booking: CounterBooking
  headingRef: RefObject<HTMLHeadingElement | null>
}) {
  const [tried, setTried] = useState(false)
  const busy = booking.pending !== null
  const refusal = booking.failure?.action === 'price' ? booking.failure.refusal : null
  const fields = refusal?.kind === 'refused' ? refusal.fields : NO_FIELD_ERRORS
  const problems = tried ? draftProblems(draft, today) : {}
  const period = periodIsUsable(draft) ? { from: draft.from, to: draft.to } : null
  const shownFields = [
    'from',
    'to',
    'branchCode',
    'customerProfileId',
    ...draft.lines.flatMap((_, index) => [`lines.${index}.quantity`, `lines.${index}.modelSlug`]),
  ]
  const fromError = problems.from ?? fields.from
  const toError = problems.to ?? fields.to
  const leftOver = otherFieldMessages(fields, shownFields)

  function price() {
    setTried(true)
    if (Object.keys(draftProblems(draft, today)).length > 0) return
    booking.price(draft)
  }

  return (
    <>
      <StepHeading headingRef={headingRef}>Step 1 of 4. Choose the dates and the tools</StepHeading>

      <Card title="When" className="mb-lg">
        <fieldset className="grid gap-md sm:grid-cols-2" disabled={busy}>
          <legend className="sr-only">The dates of the whole hire</legend>
          <DateInput
            id="booking-from"
            label="Goes out on"
            value={draft.from}
            min={today}
            error={fromError}
            onChange={(from) => onDraft({ ...draft, from })}
          />
          <DateInput
            id="booking-to"
            label="Comes back on"
            value={draft.to}
            min={draft.from}
            help={RETURN_HELP}
            error={toError}
            onChange={(to) => onDraft({ ...draft, to })}
          />
        </fieldset>
        <p className="mt-md text-sm text-slate-soft">
          Collected from {branch.name}, the branch you are working at.
          {fields.branchCode ? ` ${fields.branchCode}` : ''}
        </p>
      </Card>

      <Card title="Tools on this booking" className="mb-lg">
        {draft.lines.length === 0 ? (
          <p className={`text-sm ${problems.lines ? 'font-medium text-status-overdue' : 'text-slate-soft'}`}>
            {problems.lines ?? 'No tools yet. Find one below and add it.'}
          </p>
        ) : (
          <ul className="flex flex-col gap-sm">
            {draft.lines.map((line, index) => (
              <LineEditor
                key={line.modelSlug}
                line={line}
                position={index + 1}
                branch={branch}
                period={period}
                error={lineError(fields, index)}
                disabled={busy}
                onQuantity={(quantity) =>
                  onDraft({ ...draft, lines: withQuantity(draft.lines, line.modelSlug, quantity) })
                }
                onRemove={() => onDraft({ ...draft, lines: withoutModel(draft.lines, line.modelSlug) })}
              />
            ))}
          </ul>
        )}
      </Card>

      <Card title="Add a tool" className="mb-lg">
        <ModelFinder
          branch={branch}
          period={period}
          chosenSlugs={draft.lines.map((line) => line.modelSlug)}
          disabled={busy}
          onAdd={(model: ModelSummary) => onDraft({ ...draft, lines: withModel(draft.lines, model) })}
        />
      </Card>

      {refusal !== null && refusal.kind === 'fault' && (
        <div className="mb-md">
          <ErrorState heading="We could not work out the cost" error={refusal.error} onRetry={price} />
        </div>
      )}
      {refusal !== null && refusal.kind !== 'fault' && refusal.kind !== 'accountOnHold' && (
        <div className="mb-md">
          <Notice tone="error" title="We cannot book those details">
            <p>{refusal.detail}</p>
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

      <div className="flex flex-wrap items-center gap-sm">
        <button type="button" className="btn-primary px-lg" disabled={busy} onClick={price}>
          {booking.pending === 'price' ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
          ) : (
            <Calculator className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          {booking.pending === 'price' ? 'Working out the cost' : 'Work out the cost'}
        </button>
        <p className="text-sm text-slate-soft">Nothing is held until the next step.</p>
      </div>
    </>
  )
}
