/**
 * One write to the owner's catalogue, as one request. Adding or changing a
 * category, switching one on or off, adding or changing a model, and showing
 * a model to customers or hiding it.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server and changed a rate.
 *
 * Once the server has answered, the catalogue is marked out of date, so the
 * owner's lists and the catalogue customers browse are read again with the
 * change in them. A 409 means the record moved on since it was read, so the
 * catalogue is read again for that too. Every rule is the server's, and the
 * failure says which of them refused.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { forgetTheCatalogue } from '../../shared/api/admin-queries'
import { logEvent } from '../../shared/api/log'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { describeCounterFailure } from '../counter/counter-refusal'
import type { CounterRefusal } from '../counter/counter-refusal'

/** What the write is, for the log. */
export type CatalogueWriteKind =
  | 'category_created'
  | 'category_changed'
  | 'category_switched'
  | 'model_created'
  | 'model_changed'
  | 'model_publication'

/** What to do with the server's answer. */
export interface WriteOutcome<Answer> {
  /** Called with the answer once the server has given it. */
  onAnswer: (answer: Answer) => void
  /** Called with a message for each refused field when the server answered
   *  422, so a form can put each one under its field. */
  onRefused?: (fields: FieldErrors) => void
}

export interface CatalogueWrite {
  /** True while the request is in flight. */
  pending: boolean
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  /** Send the write. Nothing happens while another is in flight. */
  send: <Answer>(write: () => Promise<Answer>, outcome: WriteOutcome<Answer>) => void
  /** Put the failure away, when the person goes back to change something. */
  clearFailure: () => void
}

/**
 * @param kind What the write is, for the log.
 * @param subject The key of the record written, or `new`, for the log.
 */
export function useCatalogueWrite(kind: CatalogueWriteKind, subject: string): CatalogueWrite {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send<Answer>(write: () => Promise<Answer>, outcome: WriteOutcome<Answer>): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    let answer: Answer
    try {
      answer = await write()
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      logEvent('warn', 'admin.catalogue_write_refused', { kind, subject, refusal: refusal.kind })
      if (refusal.kind === 'conflict') forgetTheCatalogue(queryClient)
      if (refusal.kind === 'refused') outcome.onRefused?.(refusal.fields)
      setFailure(refusal)
      return
    } finally {
      inFlight.current = false
      setPending(false)
    }
    logEvent('info', 'admin.catalogue_written', { kind, subject })
    forgetTheCatalogue(queryClient)
    outcome.onAnswer(answer)
  }

  return {
    pending,
    failure,
    send: (write, outcome) => void send(write, outcome),
    clearFailure: () => setFailure(null),
  }
}
