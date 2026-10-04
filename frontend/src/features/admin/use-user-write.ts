/**
 * One write of SC-23, as one request. Opening a staff account, changing one,
 * deactivating or reactivating one, or moving a customer's standing.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server and opened the account.
 *
 * Once the server has answered, whatever the write changed is marked out of
 * date and read again. A 409 means the account or the customer moved on since
 * it was read, or that the server will not make the move, so those are read
 * again for that too. Every rule is the server's, and the failure says which of
 * them refused.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { forgetTheHolds, forgetTheStaff } from '../../shared/api/admin-queries'
import { logEvent } from '../../shared/api/log'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { describeCounterFailure } from '../counter/counter-refusal'
import type { CounterRefusal } from '../counter/counter-refusal'

/** What the write is, for the log. */
export type UserWriteKind =
  | 'staff_opened'
  | 'staff_changed'
  | 'staff_deactivated'
  | 'staff_reactivated'
  | 'customer_standing_set'

/** What each kind of write puts out of date. */
const FORGET: Record<UserWriteKind, (client: QueryClient) => void> = {
  staff_opened: forgetTheStaff,
  staff_changed: forgetTheStaff,
  staff_deactivated: forgetTheStaff,
  staff_reactivated: forgetTheStaff,
  customer_standing_set: forgetTheHolds,
}

/** What to do with the server's answer. */
export interface UserWriteOutcome<Answer> {
  /** Called with the answer once the server has given it. */
  onAnswer: (answer: Answer) => void
  /** Called with a message for each refused field when the server answered
   *  422, so a form can put each one under its field. */
  onRefused?: (fields: FieldErrors) => void
}

export interface UserWrite {
  /** True while the request is in flight. */
  pending: boolean
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  /** Send the write. Nothing happens while another is in flight. */
  send: <Answer>(write: () => Promise<Answer>, outcome: UserWriteOutcome<Answer>) => void
  /** Put the failure away, when the person goes back to change something. */
  clearFailure: () => void
}

/**
 * @param kind What the write is, for the log and for what it puts out of date.
 * @param subject The key of the account or the customer, or `new`, for the log.
 */
export function useUserWrite(kind: UserWriteKind, subject: string): UserWrite {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send<Answer>(write: () => Promise<Answer>, outcome: UserWriteOutcome<Answer>): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    logEvent('info', 'admin.user_write_sent', { kind, subject })
    let answer: Answer
    try {
      answer = await write()
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      // The server's sentence can name a person, so the log keeps its kind only.
      logEvent(refusal.kind === 'fault' ? 'error' : 'warn', 'admin.user_write_refused', {
        kind,
        subject,
        refusal: refusal.kind,
      })
      if (refusal.kind === 'conflict') FORGET[kind](queryClient)
      if (refusal.kind === 'refused') outcome.onRefused?.(refusal.fields)
      setFailure(refusal)
      return
    } finally {
      inFlight.current = false
      setPending(false)
    }
    logEvent('info', 'admin.user_written', { kind, subject })
    FORGET[kind](queryClient)
    outcome.onAnswer(answer)
  }

  return {
    pending,
    failure,
    send: (write, outcome) => void send(write, outcome),
    clearFailure: () => setFailure(null),
  }
}
