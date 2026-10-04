/**
 * The moves of a unit through its lifecycle, on SC-21.
 *
 * The buttons are exactly the server's `allowedTransitions` for the unit, in
 * the order it sent them, each in words. The browser holds no copy of the
 * lifecycle rules. A unit the server offers no move for says so.
 *
 * Each move asks first in a question of its own, which says what the move
 * does, and asks why where the contract asks for a reason. Retiring says
 * plainly that the unit leaves the fleet for good and that its row and its
 * history are kept. One press of the answer sends one request, and it is
 * disabled while it is in flight. A 409 or a 403 shows the server's sentence,
 * and a booking that sentence names is a link to its checkout, where the owner
 * can release the unit from it. A refused reason shows its message under the
 * box. Putting the question away gives focus back to the button that opened it.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { moveAsset } from '../../shared/api/admin-assets'
import type { AdminAssetDetail, AssetStatus, AssetTransitionRequest } from '../../shared/api/contract'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { REASON_HELP, reasonProblem } from '../counter/correction-model'
import { TextArea } from '../counter/counter-fields'
import { moveWords, sentenceWithBookings } from './asset-words'
import { useAssetWrite } from './use-asset-write'

/** What a reason for a move is read with later, in its history and the trail. */
const REASON_IS_READ_WITH = 'the history of this unit'

/** The server's sentence, with every booking it names as a link to its checkout. */
function ServerSentence({ sentence }: { sentence: string }) {
  return (
    <p className="break-words">
      {sentenceWithBookings(sentence).map((part, index) =>
        part.href === null ? (
          <span key={index}>{part.text}</span>
        ) : (
          <Link key={index} to={part.href} className="font-mono underline">
            {part.text}
          </Link>
        ),
      )}
    </p>
  )
}

function MoveQuestion({
  unit,
  to,
  onMoved,
  onCancel,
}: {
  unit: AdminAssetDetail
  to: AssetStatus
  onMoved: (unit: AdminAssetDetail, to: AssetStatus) => void
  onCancel: () => void
}) {
  const words = moveWords(to)
  const write = useAssetWrite('unit_moved', unit.assetTag)
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const failure = write.failure
  const refusedReason = failure?.kind === 'refused' ? failure.fields.reason : undefined
  const otherRefusals =
    failure?.kind === 'refused' ? Object.entries(failure.fields).filter(([field]) => field !== 'reason' || !words.asksForAReason) : []
  // A refusal of the reason alone is said under the box. Anything else the
  // server refused is said above the buttons, in its own words.
  const reasonOnly = failure?.kind === 'refused' && refusedReason !== undefined && otherRefusals.length === 0
  const id = `move-${to}`

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    let body: AssetTransitionRequest = { to }
    if (words.asksForAReason) {
      const found = reasonProblem(reason, REASON_IS_READ_WITH)
      setProblem(found)
      if (found !== null) return
      body = { to, reason: reason.trim() }
    }
    write.send(() => moveAsset(unit.assetTag, body), { onAnswer: (moved) => onMoved(moved, to) })
  }

  return (
    <form
      noValidate
      onSubmit={send}
      aria-labelledby={`${id}-heading`}
      className="min-w-0 rounded-lg border-2 border-ink bg-surface p-md"
    >
      <h4 id={`${id}-heading`} ref={headingRef} tabIndex={-1} className="break-words text-base font-semibold text-ink">
        {words.question(unit.assetTag)}
      </h4>
      <p id={`${id}-consequence`} className="mt-xs break-words text-sm text-ink">
        {words.consequence(unit)}
      </p>
      {words.asksForAReason && (
        <div className="mt-md">
          <TextArea
            id={`${id}-reason`}
            label="Why"
            help={REASON_HELP}
            value={reason}
            onChange={(value) => {
              setReason(value)
              setProblem(null)
            }}
            error={problem ?? refusedReason}
            disabled={write.pending}
            rows={2}
          />
        </div>
      )}
      {failure !== null && failure.kind !== 'fault' && !reasonOnly && (
        <div className="mt-md">
          <Notice tone="error" title={`${unit.assetTag} was not moved`}>
            <ServerSentence sentence={failure.detail} />
            {otherRefusals.length > 0 && (
              <ul className="mt-xs list-disc pl-lg">
                {otherRefusals.map(([field, message]) => (
                  <li key={field}>{message}</li>
                ))}
              </ul>
            )}
          </Notice>
        </div>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading={`We could not move ${unit.assetTag}`} error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md" disabled={write.pending} aria-describedby={`${id}-consequence`}>
          {write.pending ? words.pending : words.answer}
        </button>
        <button
          type="button"
          className="btn-secondary px-md"
          disabled={write.pending}
          onClick={() => {
            write.clearFailure()
            onCancel()
          }}
        >
          Keep it as it is
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? `${words.pending}, please wait.` : ''}
      </p>
    </form>
  )
}

export function AssetMoves({
  unit,
  onMoved,
}: {
  unit: AdminAssetDetail
  /** Called with the unit the server answered with, and the status it was moved to. */
  onMoved: (unit: AdminAssetDetail, to: AssetStatus) => void
}) {
  const [asking, setAsking] = useState<AssetStatus | null>(null)
  // The move whose question was put away unanswered, so focus can go back to
  // its button once that button is on the page again.
  const putAway = useRef<AssetStatus | null>(null)
  const buttons = useRef(new Map<AssetStatus, HTMLButtonElement>())

  useEffect(() => {
    if (asking !== null || putAway.current === null) return
    buttons.current.get(putAway.current)?.focus()
    putAway.current = null
  }, [asking])

  if (unit.allowedTransitions.length === 0) {
    return <p className="text-sm text-slate-soft">There is no move to make by hand from where this unit stands.</p>
  }
  if (asking !== null) {
    return (
      <MoveQuestion
        key={asking}
        unit={unit}
        to={asking}
        onMoved={(moved, to) => {
          setAsking(null)
          onMoved(moved, to)
        }}
        onCancel={() => {
          putAway.current = asking
          setAsking(null)
        }}
      />
    )
  }
  return (
    <ul className="flex flex-wrap gap-sm" aria-label={`What can be done with ${unit.assetTag}`}>
      {unit.allowedTransitions.map((to) => (
        <li key={to}>
          <button
            ref={(button) => {
              if (button === null) buttons.current.delete(to)
              else buttons.current.set(to, button)
            }}
            type="button"
            className={to === 'RETIRED' ? 'btn-danger px-md' : 'btn-secondary px-md'}
            onClick={() => setAsking(to)}
          >
            {moveWords(to).action}
          </button>
        </li>
      ))}
    </ul>
  )
}
