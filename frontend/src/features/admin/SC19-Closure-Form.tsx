/**
 * The form on the trading calendar that closes a branch, or every branch, on a
 * day.
 *
 * The owner chooses the branch, the day and the reason customers read, up to a
 * hundred and twenty characters with a count of what is left. The form checks
 * what it can at once and puts each problem under its field, with focus on the
 * first. Then it asks the server which bookings start or end on that day, and
 * shows the question that lists them before anything is written. Going back
 * from the question keeps what was typed.
 *
 * A field the server refuses, whether it was asked for the bookings or asked
 * to close the day, shows the server's sentence under that field. Any other
 * failure to read the bookings is said above the button with a way to try
 * again.
 */

import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { readClosureImpact } from '../../shared/api/closure-days'
import type { ClosureDay, ClosureImpact } from '../../shared/api/contract'
import { fieldErrorsFromProblem, isRefusal, otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { DateInput, SelectInput, TextInput } from '../counter/counter-fields'
import {
  EVERY_BRANCH,
  EVERY_BRANCH_VALUE,
  branchCodeOf,
  draftProblems,
  reasonCounter,
} from './calendar-words'
import type { ClosureDraft, DraftProblems } from './calendar-words'
import { ClosureQuestion } from './SC19-Closure-Question'
import type { ClosureAsked } from './SC19-Closure-Question'
import type { BranchList } from './use-branch-list'

const FORM_ID = 'closure'
const EMPTY_DRAFT: ClosureDraft = { branch: '', day: '', reason: '' }
/** The fields of the form, in order, as the API names them. */
const SERVER_FIELDS = ['branchCode', 'day', 'reason'] as const
/** The id of each field's control, by the name the draft gives it. */
const CONTROL_ID: Record<keyof ClosureDraft, string> = {
  branch: `${FORM_ID}-branch`,
  day: `${FORM_ID}-day`,
  reason: `${FORM_ID}-reason`,
}

interface Asked {
  asked: ClosureAsked
  impact: ClosureImpact
}

export function ClosureForm({
  today,
  branches,
  onClosed,
}: {
  today: string
  branches: BranchList
  /** Called with the closure the server answered with. */
  onClosed: (closure: ClosureDay) => void
}) {
  const [draft, setDraft] = useState<ClosureDraft>(EMPTY_DRAFT)
  const [problems, setProblems] = useState<DraftProblems>({})
  const [refused, setRefused] = useState<FieldErrors>({})
  const [checking, setChecking] = useState(false)
  const [checkFailure, setCheckFailure] = useState<unknown>(null)
  const [question, setQuestion] = useState<Asked | null>(null)
  const inFlight = useRef(false)
  const submitRef = useRef<HTMLButtonElement>(null)
  const others = otherFieldMessages(refused, SERVER_FIELDS)

  const branchOptions = [
    { value: '', label: 'Choose a branch' },
    { value: EVERY_BRANCH_VALUE, label: EVERY_BRANCH },
    ...branches.options,
  ]

  function change(field: keyof ClosureDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }))
    setProblems((current) => ({ ...current, [field]: undefined }))
    setRefused({})
  }

  function askedFor(): ClosureAsked {
    const branchCode = branchCodeOf(draft)
    return {
      branchCode,
      branchLabel: branchCode === null ? EVERY_BRANCH : branches.nameOf(branchCode),
      day: draft.day,
      reason: draft.reason.trim(),
    }
  }

  async function check(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current) return
    const found = draftProblems(draft, today)
    setProblems(found)
    setRefused({})
    setCheckFailure(null)
    const first = (Object.keys(CONTROL_ID) as (keyof ClosureDraft)[]).find((field) => found[field] !== undefined)
    if (first !== undefined) {
      document.getElementById(CONTROL_ID[first])?.focus()
      return
    }
    const asked = askedFor()
    inFlight.current = true
    setChecking(true)
    try {
      const query = asked.branchCode === null ? { day: asked.day } : { day: asked.day, branchCode: asked.branchCode }
      setQuestion({ asked, impact: await readClosureImpact(query) })
    } catch (cause) {
      if (isRefusal(cause)) setRefused(fieldErrorsFromProblem(cause))
      else setCheckFailure(cause)
    } finally {
      inFlight.current = false
      setChecking(false)
    }
  }

  if (question !== null) {
    return (
      <ClosureQuestion
        asked={question.asked}
        impact={question.impact}
        onClosed={(closure) => {
          setQuestion(null)
          setDraft(EMPTY_DRAFT)
          onClosed(closure)
        }}
        onRefused={(fields) => {
          setQuestion(null)
          setRefused(fields)
        }}
        onBack={() => {
          setQuestion(null)
          // The form is drawn again on the next paint, and its button then takes focus.
          requestAnimationFrame(() => submitRef.current?.focus())
        }}
      />
    )
  }

  return (
    <form noValidate onSubmit={(event) => void check(event)} aria-label="Close a day" className="card p-lg">
      <div className="grid gap-md sm:grid-cols-2">
        <SelectInput
          id={CONTROL_ID.branch}
          label="Branch"
          value={draft.branch}
          onChange={(value) => change('branch', value)}
          options={branchOptions}
          error={problems.branch ?? refused.branchCode}
          help={branches.failed ? 'The branch names could not be read. Every branch can still be chosen.' : undefined}
          disabled={checking}
        />
        <DateInput
          id={CONTROL_ID.day}
          label="Day to close"
          value={draft.day}
          min={today}
          onChange={(value) => change('day', value)}
          help="Today or a day up to a year ahead."
          error={problems.day ?? refused.day}
        />
      </div>
      <div className="mt-md">
        <TextInput
          id={CONTROL_ID.reason}
          label="Reason customers read"
          value={draft.reason}
          onChange={(value) => change('reason', value)}
          help={`For example, stocktake or election day. ${reasonCounter(draft.reason)}`}
          error={problems.reason ?? refused.reason}
          disabled={checking}
          autoComplete="off"
        />
      </div>
      {others.length > 0 && (
        <div className="mt-md">
          <Notice tone="error" title="The day was not closed">
            <ul className="list-disc pl-lg">
              {others.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </Notice>
        </div>
      )}
      {checkFailure !== null && (
        <div className="mt-md">
          <ErrorState heading="We could not read the bookings on that day" error={checkFailure} />
        </div>
      )}
      <div className="mt-md">
        <button ref={submitRef} type="submit" className="btn-primary px-md" disabled={checking}>
          {checking ? 'Checking the bookings on that day' : 'Check the bookings and close the day'}
        </button>
      </div>
      <p role="status" className="sr-only">
        {checking ? 'Checking the bookings on that day, please wait.' : ''}
      </p>
    </form>
  )
}
