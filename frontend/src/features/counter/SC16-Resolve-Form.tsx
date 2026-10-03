/**
 * The owner's form for resolving one damage report on SC-16.
 *
 * It asks for the outcome, repaired or written off, with neither chosen, the
 * actual repair cost, which a repair needs, and notes. Under them it says in
 * words what will happen to the unit, and the words follow the outcome as it
 * is chosen. One press sends one request to the resolution route, and the
 * button is disabled while it is in flight.
 *
 * A 422 puts the server's message under the control it names. A 409, such as a
 * write off while the unit is set aside for a booking, or a 403 shows the
 * server's sentence. The rules and the body are in SC16-resolve-model.ts.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { CheckCircle2 } from 'lucide-react'
import type { DamageOutcome, DamageReport } from '../../shared/api/contract'
import { resolveDamageReport } from '../../shared/api/damage-reports'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { ProblemList, TextArea, TextInput } from './counter-fields'
import { OUTCOME_OPTIONS } from './SC16-damage-choices'
import { ChoiceGroup } from './SC16-DamageFields'
import {
  EMPTY_RESOLVE_DRAFT,
  resolutionWords,
  resolveControlId,
  serverResolveErrors,
  toResolveRequest,
  validateResolution,
} from './SC16-resolve-model'
import type { ResolveControl, ResolveDraft, ResolveErrors } from './SC16-resolve-model'
import { useDamageWrite } from './use-damage-write'

const NO_ERRORS: ResolveErrors = {}

const CONTROL_ORDER: readonly ResolveControl[] = ['outcome', 'cost', 'notes']

const NOTES_ROWS = 3

/** The words on the button, which say what it will do. */
function submitLabel(outcome: DamageOutcome | null): string {
  if (outcome === 'RESOLVED') return 'Resolve as repaired'
  if (outcome === 'WRITTEN_OFF') return 'Write the unit off'
  return 'Resolve the report'
}

export function ResolveForm({
  report,
  onResolved,
  onCancel,
}: {
  report: DamageReport
  /** Called with the report the server answered with. */
  onResolved: (report: DamageReport) => void
  onCancel: () => void
}) {
  const write = useDamageWrite(report.reference, 'resolution')
  const [draft, setDraft] = useState<ResolveDraft>(EMPTY_RESOLVE_DRAFT)
  const [tried, setTried] = useState(false)
  const failure = write.failure
  const server = failure?.kind === 'refused' ? serverResolveErrors(failure.fields) : null
  const clientErrors = validateResolution(draft)
  const errors: ResolveErrors = { ...(tried ? clientErrors : NO_ERRORS), ...(server?.byControl ?? NO_ERRORS) }
  const headingId = `resolve-${report.id}-heading`
  const problems = CONTROL_ORDER.flatMap((control) => {
    const message = errors[control]
    return message === undefined ? [] : [{ id: resolveControlId(report.id, control), message }]
  })
  const leftOver = server === null ? [] : server.leftOver
  if (failure?.kind === 'refused' && problems.length === 0 && leftOver.length === 0) leftOver.push(failure.detail)

  // The form opens in place of its button, so focus goes to its heading.
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [])

  function patch(change: Partial<ResolveDraft>) {
    setDraft((current) => ({ ...current, ...change }))
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTried(true)
    write.clearFailure()
    if (Object.keys(clientErrors).length > 0) return
    const body = toResolveRequest(draft)
    write.send(() => resolveDamageReport(report.id, body), onResolved)
  }

  const count = problems.length + leftOver.length
  return (
    <form noValidate onSubmit={submit} aria-labelledby={headingId} className="mt-md rounded-lg border-2 border-ink p-md">
      <h4 id={headingId} ref={heading} tabIndex={-1} className="text-base font-semibold text-ink">
        Resolve {report.reference}
      </h4>
      {count > 0 && (
        <div className="mt-sm">
          <Notice tone="error" title={`Nothing has been sent yet. ${count} ${count === 1 ? 'answer needs' : 'answers need'} fixing.`}>
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
      <div className="mt-md flex flex-col gap-md">
        <ChoiceGroup
          id={resolveControlId(report.id, 'outcome')}
          legend="How was it resolved"
          options={OUTCOME_OPTIONS}
          value={draft.outcome}
          onChange={(outcome) => patch({ outcome })}
          error={errors.outcome}
          columns={2}
          disabled={write.pending}
        />
        <TextInput
          id={resolveControlId(report.id, 'cost')}
          label="Actual repair cost, in rand"
          help={
            draft.outcome === 'WRITTEN_OFF'
              ? 'Optional for a write off. What was spent on the unit, if anything.'
              : 'Required for a repair, for example 380.00.'
          }
          inputMode="decimal"
          autoComplete="off"
          value={draft.cost}
          onChange={(cost) => patch({ cost })}
          error={errors.cost}
          disabled={write.pending}
        />
        <TextArea
          id={resolveControlId(report.id, 'notes')}
          label="Notes"
          help="Optional. What the workshop did, or why the unit was written off."
          rows={NOTES_ROWS}
          value={draft.notes}
          onChange={(notes) => patch({ notes })}
          error={errors.notes}
          disabled={write.pending}
        />
        <p className="rounded bg-muted p-sm text-sm text-ink" aria-live="polite">
          {resolutionWords(draft.outcome, report.assetTag)}
        </p>
      </div>
      {failure !== null && failure.kind !== 'fault' && failure.kind !== 'refused' && (
        <div className="mt-md">
          <Notice tone="error" title="The report was not resolved">
            <p>{failure.detail}</p>
          </Notice>
        </div>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading="We could not resolve the report" error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md" disabled={write.pending}>
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          {write.pending ? 'Resolving the report' : submitLabel(draft.outcome)}
        </button>
        <button type="button" className="btn-secondary px-md" disabled={write.pending} onClick={onCancel}>
          Cancel
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? 'Resolving the report, please wait.' : ''}
      </p>
    </form>
  )
}
