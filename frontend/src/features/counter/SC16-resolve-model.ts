/**
 * How the owner resolves a damage report on SC-16. The rules the form is
 * checked against, the body it is sent as, and what it says will happen to the
 * unit.
 *
 * The owner chooses an outcome, repaired or written off, and nothing is chosen
 * for them, because a write off cannot be undone. The actual repair cost is
 * required for a repair and may be left empty for a write off. The notes may
 * be left empty. The server has the last word, and refuses a write off with a
 * 409 while the unit is set aside for a booking (BR-37).
 */

import type { DamageOutcome, ResolveDamageReportRequest } from '../../shared/api/contract'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { typedRand } from './SC16-damage-model'

/** What the owner has recorded so far. */
export interface ResolveDraft {
  outcome: DamageOutcome | null
  /** The actual repair cost as typed. */
  cost: string
  notes: string
}

export type ResolveControl = 'outcome' | 'cost' | 'notes'

/** A message for each control that needs fixing. */
export type ResolveErrors = Readonly<Partial<Record<ResolveControl, string>>>

export const EMPTY_RESOLVE_DRAFT: ResolveDraft = { outcome: null, cost: '', notes: '' }

/** The id of each control of the form for one report. Every report on the
 *  screen has its own form, so the ids carry its key. */
export function resolveControlId(reportId: string, control: ResolveControl): string {
  return `resolve-${reportId}-${control}`
}

const COST_MESSAGE = 'Enter what the repair actually cost in rand, for example 380.00.'

/**
 * Check the form before it is sent.
 *
 * @returns A sentence for each control that needs fixing.
 */
export function validateResolution(draft: ResolveDraft): ResolveErrors {
  const errors: Partial<Record<ResolveControl, string>> = {}
  if (draft.outcome === null) errors.outcome = 'Choose whether the unit was repaired or written off.'
  const typed = draft.cost.trim()
  const required = draft.outcome === 'RESOLVED'
  if ((required || typed !== '') && typedRand(typed) === null) errors.cost = COST_MESSAGE
  return errors
}

/**
 * The body the form is sent as, with null for a cost or notes left empty.
 *
 * @throws Error when no outcome is chosen. `validateResolution` refuses that
 *   form, so reaching here with one is a defect in the screen.
 */
export function toResolveRequest(draft: ResolveDraft): ResolveDamageReportRequest {
  if (draft.outcome === null) {
    throw new Error(
      'Tried to build a resolution body with no outcome chosen. validateResolution refuses that form, ' +
        'so the screen should not have sent it.',
    )
  }
  const notes = draft.notes.trim()
  return {
    outcome: draft.outcome,
    actualRepairCost: typedRand(draft.cost.trim()),
    resolutionNotes: notes === '' ? null : notes,
  }
}

/** What the outcome does to the unit, in words, before it is chosen for good. */
export function resolutionWords(outcome: DamageOutcome | null, assetTag: string): string {
  if (outcome === 'RESOLVED') {
    return `${assetTag} goes back on the shelf and can be booked again, unless another report on it is still open.`
  }
  if (outcome === 'WRITTEN_OFF') {
    return (
      `${assetTag} is retired from the fleet today and can never be hired again, which cannot be undone. ` +
      'The server refuses it while the unit is set aside for a booking.'
    )
  }
  return 'Choose how the report was resolved, and the screen says what happens to the unit.'
}

/** Both spellings of each field the API may name, as on the damage form. */
const API_FIELD_CONTROL: Record<string, ResolveControl> = {
  outcome: 'outcome',
  actualRepairCost: 'cost',
  actual_repair_cost: 'cost',
  resolutionNotes: 'notes',
  resolution_notes: 'notes',
}

/**
 * Put each message the API sent under the control it is about.
 *
 * @returns The messages by control, and the ones no control shows.
 */
export function serverResolveErrors(fields: FieldErrors): { byControl: ResolveErrors; leftOver: string[] } {
  const byControl: Partial<Record<ResolveControl, string>> = {}
  const leftOver: string[] = []
  for (const [name, message] of Object.entries(fields)) {
    const control = API_FIELD_CONTROL[name]
    if (control !== undefined) byControl[control] = message
    else leftOver.push(message)
  }
  return { byControl, leftOver }
}
