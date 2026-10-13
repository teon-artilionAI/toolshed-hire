/**
 * One write of the trading calendar, as one request. Closing a day, or
 * cancelling a closure, which opens the day again.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server and closed the day.
 *
 * Once the server has answered, everything that knows which days a branch
 * trades is marked out of date and read again, the calendar, the branch list
 * every date picker steers by, and the counter's day. A 409 means the day was
 * closed or opened by somebody else since the list was read, so those are read
 * again for that too. Every rule is the server's, and the failure says which of
 * them refused.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { forgetTheCalendar } from '../../shared/api/admin-queries'
import { logEvent } from '../../shared/api/log'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { describeCounterFailure } from '../counter/counter-refusal'
import type { CounterRefusal } from '../counter/counter-refusal'

/** What the write is, for the log. */
export type ClosureWriteKind = 'closure_added' | 'closure_cancelled'

/** What to do with the server's answer. */
export interface ClosureWriteOutcome<Answer> {
  /** Called with the answer once the server has given it. */
  onAnswer: (answer: Answer) => void
  /** Called with a message for each refused field when the server answered
   *  422, so a form can put each one under its field. */
  onRefused?: (fields: FieldErrors) => void
}

export interface ClosureWrite {
  /** True while the request is in flight. */
  pending: boolean
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  /** Send the write. Nothing happens while another is in flight. */
  send: <Answer>(write: () => Promise<Answer>, outcome: ClosureWriteOutcome<Answer>) => void
  /** Put the failure away, when the person goes back to change something. */
  clearFailure: () => void
}

/**
 * @param kind What the write is, for the log.
 * @param subject The key of the closure, or `new`, for the log.
 */
export function useClosureWrite(kind: ClosureWriteKind, subject: string): ClosureWrite {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send<Answer>(write: () => Promise<Answer>, outcome: ClosureWriteOutcome<Answer>): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    logEvent('info', 'admin.closure_write_sent', { kind, subject })
    let answer: Answer
    try {
      answer = await write()
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      logEvent(refusal.kind === 'fault' ? 'error' : 'warn', 'admin.closure_write_refused', {
        kind,
        subject,
        refusal: refusal.kind,
      })
      if (refusal.kind === 'conflict') forgetTheCalendar(queryClient)
      if (refusal.kind === 'refused') outcome.onRefused?.(refusal.fields)
      setFailure(refusal)
      return
    } finally {
      inFlight.current = false
      setPending(false)
    }
    logEvent('info', 'admin.closure_written', { kind, subject })
    forgetTheCalendar(queryClient)
    outcome.onAnswer(answer)
  }

  return {
    pending,
    failure,
    send: (write, outcome) => void send(write, outcome),
    clearFailure: () => setFailure(null),
  }
}
