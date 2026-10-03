/**
 * One write to a damage report, as one request. Filing a report, sending one
 * for repair, or resolving one.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server and raised the charge.
 *
 * Every write answers with the report as the server now has it. What it
 * changed is then marked out of date through `rememberDamageReport`, which
 * also drops the hire the report belongs to from the cache, so the return
 * screen reads it afresh. A 409 means the report or the unit moved on since it
 * was read, so the reports are read again as well.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { DamageReport } from '../../shared/api/contract'
import { forgetDamageReports, rememberDamageReport } from '../../shared/api/damage-queries'
import { logEvent } from '../../shared/api/log'
import { describeCounterFailure } from './counter-refusal'
import type { CounterRefusal } from './counter-refusal'

/** What the write is, for the log. */
export type DamageWriteKind = 'file' | 'repair' | 'resolution'

export interface DamageWrite {
  /** True while the request is in flight. */
  pending: boolean
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  /**
   * Send the write. Nothing happens while another is in flight.
   *
   * @param write Makes the one request.
   * @param onWritten Called with the report the server answered with.
   */
  send: (write: () => Promise<DamageReport>, onWritten: (report: DamageReport) => void) => void
  /** Put the failure away, when the person goes back to change something. */
  clearFailure: () => void
}

/**
 * @param subject The unit or the report the write is about, for the log.
 * @param kind What the write is, for the log.
 */
export function useDamageWrite(subject: string, kind: DamageWriteKind): DamageWrite {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send(write: () => Promise<DamageReport>, onWritten: (report: DamageReport) => void): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    try {
      const report = await write()
      logEvent('info', 'counter.damage_written', {
        kind,
        subject,
        reference: report.reference,
        status: report.status,
        rental: report.rentalReference,
      })
      rememberDamageReport(queryClient, report)
      onWritten(report)
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      logEvent('warn', 'counter.damage_write_refused', { kind, subject, refusal: refusal.kind })
      if (refusal.kind === 'conflict') forgetDamageReports(queryClient)
      setFailure(refusal)
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  return {
    pending,
    failure,
    send: (write, onWritten) => void send(write, onWritten),
    clearFailure: () => setFailure(null),
  }
}
