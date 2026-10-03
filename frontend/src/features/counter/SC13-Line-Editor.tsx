/**
 * One line of a counter booking, for SC-13.
 *
 * A model, how many of it, and whether that many are free at this branch for
 * the whole period. The answer comes from the single model availability route,
 * which also applies the shortest and longest hire of the model, and it is
 * asked again whenever the quantity or the dates change. It says free or not
 * free and never a count.
 *
 * The units themselves are picked by the server when the booking is held.
 * Nobody chooses a unit here, so a booking can never be tied to a unit that
 * another booking already has.
 */

import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Ban, CircleCheck, Loader2, Minus, Plus, RotateCw, Trash2 } from 'lucide-react'
import { MAX_QUANTITY, MIN_QUANTITY } from '../../shared/api/catalogue'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import { queryPhase } from '../../shared/api/query-phase'
import type { DraftLine } from './booking-draft'
import { describeCounterFailure } from './counter-refusal'
import type { CounterBranch } from './work-branch-gate'

function LineAvailability({
  line,
  branch,
  period,
}: {
  line: DraftLine
  branch: CounterBranch
  /** Null while the dates cannot be asked about. */
  period: { from: string; to: string } | null
}) {
  const answer = useQuery({
    ...catalogueQueries.modelAvailability(line.modelSlug, {
      from: period?.from ?? '',
      to: period?.to ?? '',
      quantity: line.quantity,
    }),
    enabled: period !== null,
  })
  const phase = queryPhase(answer)
  const units = `${line.quantity} ${line.quantity === 1 ? 'unit' : 'units'}`

  if (period === null) {
    return <p className="text-sm text-slate-soft">Choose the dates to see whether it is free.</p>
  }
  if (phase === 'loading' || phase === 'idle') {
    return (
      <p className="flex items-center gap-xs text-sm text-slate-soft">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
        Checking {units} at {branch.name}
      </p>
    )
  }
  if (phase === 'failed') {
    const refusal = describeCounterFailure(answer.error)
    return (
      <div className="flex flex-wrap items-center gap-sm text-sm text-status-overdue">
        <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{refusal.kind === 'fault' ? 'We could not check whether it is free.' : refusal.detail}</span>
        {refusal.kind === 'fault' && (
          <button type="button" className="btn-ghost px-sm" onClick={() => void answer.refetch()}>
            <RotateCw className="h-4 w-4 shrink-0" aria-hidden="true" />
            Check again
          </button>
        )}
      </div>
    )
  }
  const here = answer.data?.branches.find((candidate) => candidate.branchCode === branch.code)
  const free = here?.available === true
  const Icon = free ? CircleCheck : Ban
  return (
    <p
      className={`flex items-start gap-xs text-sm font-medium ${
        free ? 'text-status-available' : 'text-status-overdue'
      }`}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      {free
        ? `${units} free at ${branch.name} for these dates`
        : `${units} not free at ${branch.name} for these dates. Lower the quantity, change the dates or remove it.`}
    </p>
  )
}

export default function LineEditor({
  line,
  position,
  branch,
  period,
  error,
  disabled,
  onQuantity,
  onRemove,
}: {
  line: DraftLine
  /** Where the line sits, counted from one, so each control has its own name. */
  position: number
  branch: CounterBranch
  period: { from: string; to: string } | null
  /** What the API said about this line, when it refused it. */
  error?: string
  disabled: boolean
  onQuantity: (quantity: number) => void
  onRemove: () => void
}) {
  const id = `line-${position}-quantity`
  return (
    <li className="rounded border border-line bg-surface p-md">
      <div className="flex flex-wrap items-end justify-between gap-md">
        <p className="min-w-0 break-words font-medium text-ink">
          <span className="sr-only">Tool {position}, </span>
          {line.modelName}
        </p>
        <div className="flex flex-wrap items-end gap-sm">
          <div>
            <label className="field-label" htmlFor={id}>
              How many
            </label>
            <div className="flex items-center gap-sm">
              <button
                type="button"
                className="btn-secondary w-11 shrink-0 px-0"
                disabled={disabled || line.quantity <= MIN_QUANTITY}
                onClick={() => onQuantity(line.quantity - 1)}
              >
                <Minus className="h-4 w-4" aria-hidden="true" />
                <span className="sr-only">One fewer {line.modelName}</span>
              </button>
              <input
                id={id}
                type="number"
                inputMode="numeric"
                className="field-input tabular w-20 text-center"
                value={line.quantity}
                min={MIN_QUANTITY}
                max={MAX_QUANTITY}
                disabled={disabled}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? `${id}-error` : undefined}
                onChange={(event) => onQuantity(Number.parseInt(event.target.value, 10) || MIN_QUANTITY)}
              />
              <button
                type="button"
                className="btn-secondary w-11 shrink-0 px-0"
                disabled={disabled || line.quantity >= MAX_QUANTITY}
                onClick={() => onQuantity(line.quantity + 1)}
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                <span className="sr-only">One more {line.modelName}</span>
              </button>
            </div>
          </div>
          <button type="button" className="btn-secondary px-md" disabled={disabled} onClick={onRemove}>
            <Trash2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            Remove{' '}
            <span className="sr-only">{line.modelName}</span>
          </button>
        </div>
      </div>
      {error && (
        <p className="field-error" id={`${id}-error`}>
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
      <div className="mt-sm">
        <LineAvailability line={line} branch={branch} period={period} />
      </div>
    </li>
  )
}
