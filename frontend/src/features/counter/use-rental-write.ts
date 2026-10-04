/**
 * One write to a hire, as one request. A return, a balance payment or a loss,
 * or one of the owner's corrections, which are a waiver, a reversal and an
 * adjustment.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server and settled the deposit.
 *
 * Every write answers with the whole hire as the server now has it. That goes
 * into the cache under the key and the reference of the hire, so the screen
 * showing it shows the server's figures at once, and everything the write
 * changed is marked out of date. A correction changes the owner's figures and
 * adds to the audit trail too, so those are marked out of date as well. A 409
 * means the hire moved on since it was read, so the hire is read again too.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { forgetOwnerFigures } from '../../shared/api/admin-queries'
import type { Rental } from '../../shared/api/contract'
import { logEvent } from '../../shared/api/log'
import { forgetRental, rememberRental } from '../../shared/api/rental-queries'
import { describeCounterFailure } from './counter-refusal'
import type { CounterRefusal } from './counter-refusal'

/** The owner's corrections of a hire. */
export type CorrectionKind = 'waiver' | 'reversal' | 'adjustment'

/** What the write is, for the log. For example `return` or `loss`. */
export type RentalWriteKind = 'return' | 'balance_payment' | 'loss' | CorrectionKind

const CORRECTIONS: readonly RentalWriteKind[] = ['waiver', 'reversal', 'adjustment']

export interface RentalWrite {
  /** True while the request is in flight. */
  pending: boolean
  /** The hire as the last write answered with it, once one has. */
  answered: Rental | null
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  /** Send the write. Nothing happens while another is in flight. */
  send: (write: () => Promise<Rental>) => void
  /** Put the failure away, when the person goes back to change something. */
  clearFailure: () => void
}

/**
 * @param rentalKey The key or the reference the screen opened the hire by.
 * @param kind What the write is, for the log.
 */
export function useRentalWrite(rentalKey: string, kind: RentalWriteKind): RentalWrite {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [answered, setAnswered] = useState<Rental | null>(null)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send(write: () => Promise<Rental>): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    try {
      const rental = await write()
      logEvent('info', 'counter.rental_written', {
        kind,
        rental: rentalKey,
        reference: rental.reference,
        status: rental.status,
        settlement_waiting_on: rental.settlementWaitingOn,
      })
      rememberRental(queryClient, rental)
      if (CORRECTIONS.includes(kind)) forgetOwnerFigures(queryClient)
      setAnswered(rental)
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      logEvent('warn', 'counter.rental_write_refused', { kind, rental: rentalKey, refusal: refusal.kind })
      if (refusal.kind === 'conflict') forgetRental(queryClient, rentalKey)
      setFailure(refusal)
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  return {
    pending,
    answered,
    failure,
    send: (write) => void send(write),
    clearFailure: () => setFailure(null),
  }
}
