/**
 * Recording a unit as lost, on SC-18.
 *
 * A unit more than fourteen days past its due date is in the escalation queue,
 * and this is the one thing the worklist changes. It cannot be taken back here,
 * so it asks first. The question says in words what the answer does. Fourteen
 * days of late fee are charged, the deposit for that unit is forfeited, a
 * recovery charge up to the replacement value is raised, and the unit is marked
 * lost. Only then does one button send it.
 *
 * What it did is the server's answer, which the worklist shows above its lists,
 * so it stays on the screen when the list is read again and the hire moves.
 * A 409 means the unit is back or not that late any more, and the server's
 * sentence says which.
 */

import { useEffect, useRef, useState } from 'react'
import { ArchiveX } from 'lucide-react'
import type { Rental, RentalItem } from '../../shared/api/contract'
import { LOSS_AFTER_DAYS_LATE, recordLoss } from '../../shared/api/rentals'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { itemLabel } from './SC15-return-model'
import { useRentalWrite } from './use-rental-write'

/** What the loss did, for the worklist to show. */
export interface LossOutcome {
  itemId: string
  label: string
  rental: Rental
}

/** The words of the question, which say what the answer does. */
function lossConsequence(label: string): string {
  return (
    `Recording ${label} as lost charges ${LOSS_AFTER_DAYS_LATE} days of late fee, forfeits the deposit for ` +
    'this unit, raises a recovery charge of up to its replacement value, and marks the unit as lost. It ' +
    'cannot be undone here.'
  )
}

export function LossAction({
  rental,
  item,
  onRecorded,
}: {
  rental: Rental
  item: RentalItem
  onRecorded: (outcome: LossOutcome) => void
}) {
  const label = itemLabel(item)
  const write = useRentalWrite(rental.id, 'loss')
  const [asking, setAsking] = useState(false)
  const askRef = useRef<HTMLButtonElement>(null)
  const questionRef = useRef<HTMLParagraphElement>(null)
  const askedBefore = useRef(asking)

  // Opening the question moves focus to it. Closing it puts focus back on the
  // button that opened it.
  useEffect(() => {
    if (askedBefore.current === asking) return
    askedBefore.current = asking
    if (asking) questionRef.current?.focus()
    else askRef.current?.focus()
  }, [asking])

  if (!asking) {
    return (
      <button ref={askRef} type="button" className="btn-secondary px-md" onClick={() => setAsking(true)}>
        <ArchiveX className="h-4 w-4 shrink-0" aria-hidden="true" />
        Record as lost <span className="sr-only">{label}</span>
      </button>
    )
  }

  function send() {
    write.send(async () => {
      const answered = await recordLoss(rental.id, item.id)
      onRecorded({ itemId: item.id, label, rental: answered })
      return answered
    })
  }

  const failure = write.failure
  const consequenceId = `loss-consequence-${item.id}`
  return (
    <div className="flex w-full flex-col gap-md rounded border border-line bg-muted p-md">
      <p id={consequenceId} ref={questionRef} tabIndex={-1} className="text-sm text-ink">
        {lossConsequence(label)}
      </p>
      {failure !== null && failure.kind !== 'fault' && (
        <Notice tone="error" title={`${label} was not recorded as lost`}>
          <p>{failure.detail}</p>
        </Notice>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <ErrorState heading={`We could not record ${label} as lost`} error={failure.error} onRetry={send} />
      )}
      <div className="flex flex-wrap gap-sm">
        <button
          type="button"
          className="btn-danger px-md"
          disabled={write.pending}
          aria-describedby={consequenceId}
          onClick={send}
        >
          {write.pending ? 'Recording it' : 'Yes, record it as lost'}
        </button>
        <button
          type="button"
          className="btn-secondary px-md"
          disabled={write.pending}
          onClick={() => {
            write.clearFailure()
            setAsking(false)
          }}
        >
          Keep it on the list
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? `Recording ${label} as lost, please wait.` : ''}
      </p>
    </div>
  )
}
