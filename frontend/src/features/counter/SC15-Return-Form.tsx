/**
 * Taking units back on SC-15, and the question that comes before it.
 *
 * Each unit still out can be ticked to come back now. The form is checked when
 * "Take the ticked units back" is pressed. Every problem is listed above it and
 * shown under its own control, and nothing is sent. When the form is right,
 * the question takes its place and says in words what is about to happen,
 * including every late fee the server has worked out. "Yes, take them back"
 * sends the one request, and is disabled while it is in flight.
 *
 * A 422 sends the person back to the form, with each of the server's sentences
 * under the control it names. A 409 or a 403 shows the server's sentence and
 * offers to read the hire again, because something about it has changed.
 * Anything else is the shared error state with a way to try again.
 *
 * The rules, the body and the question are in SC15-return-model.ts.
 */

import { useEffect, useRef, useState } from 'react'
import { PackageOpen, RotateCw, Undo2 } from 'lucide-react'
import type { Rental } from '../../shared/api/contract'
import { returnItems } from '../../shared/api/rentals'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { ProblemList } from './counter-fields'
import { StepHeading } from './counter-steps'
import { ItemInspection } from './SC15-ItemInspection'
import {
  UNITS_TO_RETURN_ID,
  answersFor,
  draftFor,
  itemsOut,
  returnSentences,
  returningItems,
  serverErrorsByControl,
  toReturnRequest,
  validateReturn,
} from './SC15-return-model'
import type { ItemDraft, ReturnDraft, ReturnErrors } from './SC15-return-model'
import { useRentalWrite } from './use-rental-write'

type Stage = 'filling' | 'asking'

const NO_ERRORS: ReturnErrors = {}

const RELOAD_LABEL = 'Load the hire again'

export function ReturnForm({
  rental,
  onReturned,
  onReload,
}: {
  rental: Rental
  /** Called with the hire the server answered the return with. */
  onReturned: (rental: Rental) => void
  onReload: () => void
}) {
  const write = useRentalWrite(rental.id, 'return')
  const [draft, setDraft] = useState<ReturnDraft>(() => draftFor(rental))
  const [stage, setStage] = useState<Stage>('filling')
  const [tried, setTried] = useState(false)
  const failure = write.failure
  const server = failure?.kind === 'refused' ? serverErrorsByControl(failure.fields, returningItems(rental, draft)) : null
  const clientErrors = validateReturn(rental, draft)
  const errors: ReturnErrors = { ...(tried ? clientErrors : NO_ERRORS), ...(server?.byControl ?? NO_ERRORS) }
  const problems = Object.entries(errors).map(([id, message]) => ({ id, message }))
  const leftOver = server?.leftOver ?? []

  // The form is where the screen opens. Only a change of stage moves focus, to
  // the heading of the new stage.
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

  function patchItem(itemId: string, patch: Partial<ItemDraft>) {
    setDraft((current) => {
      const item = rental.items.find((candidate) => candidate.id === itemId)
      if (!item) return current
      return { ...current, [itemId]: { ...answersFor(current, item), ...patch } }
    })
  }

  function ask() {
    setTried(true)
    write.clearFailure()
    if (Object.keys(clientErrors).length > 0) return
    setStage('asking')
  }

  function send() {
    const body = toReturnRequest(rental, draft)
    write.send(async () => {
      const answered = await returnItems(rental.id, body)
      setStage('filling')
      setTried(false)
      onReturned(answered)
      return answered
    })
  }

  if (stage === 'asking') {
    return (
      <section className="card border-2 border-ink p-lg" aria-labelledby="return-question">
        <h2 id="return-question" ref={heading} tabIndex={-1} className="text-lg font-semibold text-ink">
          Take these units back from {rental.customerName}?
        </h2>
        <div className="mt-sm flex flex-col gap-xs text-sm text-ink">
          {returnSentences(rental, draft).map((sentence) => (
            <p key={sentence}>{sentence}</p>
          ))}
        </div>
        <div className="mt-lg flex flex-wrap gap-sm">
          <button type="button" className="btn-primary px-lg" disabled={write.pending} onClick={send}>
            <PackageOpen className="h-4 w-4 shrink-0" aria-hidden="true" />
            {write.pending ? 'Taking the units back' : 'Yes, take them back'}
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
          {write.pending ? 'Taking the units back, please wait.' : ''}
        </p>
        {failure !== null && failure.kind === 'fault' && (
          <div className="mt-md">
            <ErrorState heading="We could not record the return" error={failure.error} onRetry={send}>
              <button type="button" className="btn-ghost px-md" onClick={onReload}>
                {RELOAD_LABEL}
              </button>
            </ErrorState>
          </div>
        )}
        {failure !== null && failure.kind !== 'fault' && failure.kind !== 'refused' && (
          <div className="mt-md">
            <Notice tone="error" title="The units were not taken back">
              <p>{failure.detail}</p>
              <button type="button" className="btn-secondary mt-sm px-md" onClick={onReload}>
                <RotateCw className="h-4 w-4 shrink-0" aria-hidden="true" />
                {RELOAD_LABEL}
              </button>
            </Notice>
          </div>
        )}
      </section>
    )
  }

  const count = Math.max(problems.length, leftOver.length)
  return (
    <div className="flex flex-col gap-lg">
      <StepHeading headingRef={heading}>Units still out</StepHeading>
      {(problems.length > 0 || leftOver.length > 0) && (
        <Notice tone="error" title={`Nothing has been taken back yet. ${count} ${count === 1 ? 'answer needs' : 'answers need'} fixing.`}>
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
      <section id={UNITS_TO_RETURN_ID} tabIndex={-1} aria-label="The units still out" className="flex flex-col gap-md">
        {itemsOut(rental).map((item) => (
          <ItemInspection
            key={item.id}
            item={item}
            answers={answersFor(draft, item)}
            errors={errors}
            disabled={write.pending}
            onChange={(patch) => patchItem(item.id, patch)}
          />
        ))}
      </section>
      <div>
        <button type="button" className="btn-primary px-lg" onClick={ask}>
          <PackageOpen className="h-4 w-4 shrink-0" aria-hidden="true" />
          Take the ticked units back
        </button>
      </div>
    </div>
  )
}
