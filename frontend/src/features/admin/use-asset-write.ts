/**
 * One write to the asset register, as one request. Registering a unit,
 * changing its paperwork, or moving it through its lifecycle.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server and moved a unit.
 *
 * Every write answers with the unit as the server now has it and its history.
 * That answer is kept under the tag, so the unit shows it at once, and then
 * everything the write changes is marked out of date and read again, the
 * register, the owner's figures, the trail and the counter's locator. A 409
 * means the unit moved on since it was read, so the register is read again
 * for that too. Every rule is the server's, and the failure says which of them
 * refused.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { forgetTheRegister, rememberAdminAsset } from '../../shared/api/admin-queries'
import type { AdminAssetDetail } from '../../shared/api/contract'
import { logEvent } from '../../shared/api/log'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { describeCounterFailure } from '../counter/counter-refusal'
import type { CounterRefusal } from '../counter/counter-refusal'

/** What the write is, for the log. */
export type AssetWriteKind = 'unit_registered' | 'unit_changed' | 'unit_moved'

/** What to do with the server's answer. */
export interface AssetWriteOutcome {
  /** Called with the unit once the server has answered. */
  onAnswer: (unit: AdminAssetDetail) => void
  /** Called with a message for each refused field when the server answered
   *  422, so a form can put each one under its field. */
  onRefused?: (fields: FieldErrors) => void
}

export interface AssetWrite {
  /** True while the request is in flight. */
  pending: boolean
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  /** Send the write. Nothing happens while another is in flight. */
  send: (write: () => Promise<AdminAssetDetail>, outcome: AssetWriteOutcome) => void
  /** Put the failure away, when the person goes back to change something. */
  clearFailure: () => void
}

/**
 * @param kind What the write is, for the log.
 * @param subject The tag of the unit written, or `new`, for the log.
 */
export function useAssetWrite(kind: AssetWriteKind, subject: string): AssetWrite {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send(write: () => Promise<AdminAssetDetail>, outcome: AssetWriteOutcome): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    let unit: AdminAssetDetail
    try {
      unit = await write()
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      logEvent('warn', 'admin.asset_write_refused', { kind, subject, refusal: refusal.kind })
      if (refusal.kind === 'conflict') forgetTheRegister(queryClient)
      if (refusal.kind === 'refused') outcome.onRefused?.(refusal.fields)
      setFailure(refusal)
      return
    } finally {
      inFlight.current = false
      setPending(false)
    }
    logEvent('info', 'admin.asset_written', { kind, subject, tag: unit.assetTag, status: unit.status })
    rememberAdminAsset(queryClient, unit)
    forgetTheRegister(queryClient)
    outcome.onAnswer(unit)
  }

  return {
    pending,
    failure,
    send: (write, outcome) => void send(write, outcome),
    clearFailure: () => setFailure(null),
  }
}
