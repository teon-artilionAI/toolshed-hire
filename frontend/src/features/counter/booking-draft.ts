/**
 * The booking an assistant is putting together on SC-13, before anything has
 * been asked of the server.
 *
 * It is a period and a list of models with how many of each. There is no
 * price here and no unit. The server prices the booking when it makes the
 * reservation, and picks the units when it holds it. The counter only ever
 * books for the branch the assistant works at, so the branch is not part of
 * the draft either.
 *
 * Periods are half open, `[from, to)`, like everywhere else. A hire from the
 * 6th to the 7th is one day, and the unit is free again on the 7th.
 */

import { MAX_QUANTITY, MIN_QUANTITY } from '../../shared/api/catalogue'
import type { CreateReservationRequest } from '../../shared/api/contract'
import { formatDate } from '../../shared/format'

/** A walk in at the counter usually wants the tool for the day. */
export const DEFAULT_HIRE_DAYS = 1

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

export interface DraftLine {
  modelSlug: string
  modelName: string
  quantity: number
}

export interface BookingDraft {
  from: string
  to: string
  lines: DraftLine[]
}

/** What is wrong with a draft, keyed the way the API names the fields. */
export interface DraftProblems {
  from?: string
  to?: string
  lines?: string
}

/** A date some days after another, both written `YYYY-MM-DD`. */
export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

/** Whether a string is a real calendar date written `YYYY-MM-DD`. */
export function isIsoDate(value: string): boolean {
  if (!ISO_DATE_PATTERN.test(value)) return false
  const date = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value
}

/** The draft a booking opens with. Out today, back tomorrow, no tools yet. */
export function emptyDraft(today: string): BookingDraft {
  return { from: today, to: addDays(today, DEFAULT_HIRE_DAYS), lines: [] }
}

/** Whether the period can be asked about at all. The server judges the rest. */
export function periodIsUsable(draft: Pick<BookingDraft, 'from' | 'to'>): boolean {
  return isIsoDate(draft.from) && isIsoDate(draft.to) && draft.to > draft.from
}

/**
 * Check a draft before it is sent. The API runs the same checks and more, and
 * has the last word.
 *
 * @param today The earliest day a hire may start, as `YYYY-MM-DD`.
 */
export function draftProblems(draft: BookingDraft, today: string): DraftProblems {
  const problems: DraftProblems = {}
  if (!isIsoDate(draft.from)) {
    problems.from = 'Choose the day the equipment goes out.'
  } else if (draft.from < today) {
    problems.from = `The equipment cannot go out in the past. Choose ${formatDate(today)} or later.`
  }
  if (!isIsoDate(draft.to)) {
    problems.to = 'Choose the day the equipment comes back.'
  } else if (isIsoDate(draft.from) && draft.to <= draft.from) {
    problems.to = 'The day it comes back must be after the day it goes out. A one day hire comes back the next morning.'
  }
  if (draft.lines.length === 0) {
    problems.lines = 'Add at least one tool to the booking.'
  }
  return problems
}

/** The lines with a model added, once. A model already on the booking is left as it is. */
export function withModel(lines: readonly DraftLine[], model: { slug: string; name: string }): DraftLine[] {
  if (lines.some((line) => line.modelSlug === model.slug)) return [...lines]
  return [...lines, { modelSlug: model.slug, modelName: model.name, quantity: MIN_QUANTITY }]
}

/** The lines with one quantity changed, kept between the least and the most the API takes. */
export function withQuantity(lines: readonly DraftLine[], modelSlug: string, quantity: number): DraftLine[] {
  const kept = Math.min(Math.max(MIN_QUANTITY, Math.round(quantity)), MAX_QUANTITY)
  return lines.map((line) => (line.modelSlug === modelSlug ? { ...line, quantity: kept } : line))
}

/** The lines without one model. */
export function withoutModel(lines: readonly DraftLine[], modelSlug: string): DraftLine[] {
  return lines.filter((line) => line.modelSlug !== modelSlug)
}

/**
 * The body the draft is sent as. The same route an online booking uses, with
 * the customer named, because staff book on a customer's behalf.
 */
export function toReservationRequest(
  draft: BookingDraft,
  branchCode: string,
  customerProfileId: string,
): CreateReservationRequest {
  return {
    branchCode,
    from: draft.from,
    to: draft.to,
    lines: draft.lines.map(({ modelSlug, quantity }) => ({ modelSlug, quantity })),
    customerProfileId,
    notes: null,
  }
}
