/**
 * The two panels that change something about a unit, used only by SC-21.
 *
 * Both are deliberately a step of their own rather than a menu on the row.
 * Retiring a tool and closing a damage report are decisions with money
 * attached, and they should read like decisions.
 */

import { useState } from 'react'
import { CheckCircle2, X } from 'lucide-react'
import type { Asset, AssetStatus, DamageReport, ProductModel } from '../../shared/types'
import { EmptyState, Field, Notice, StatusPill } from '../../shared/ui'
import { formatDate, money } from '../../shared/format'
import { LEAVES_THE_FLEET, LIFECYCLE, NEEDS_REASON, blockedReason, noMovesReason } from './admin-lifecycle'

const MIN_REASON_LENGTH = 8

const SEVERITY_LABEL = { MINOR: 'Minor', MODERATE: 'Moderate', SEVERE: 'Severe' }

/** Move one unit along its lifecycle, offering only the moves it may make. */
export function StatusChangePanel({
  asset, model, hasOpenDamage, onApply, onCancel,
}: {
  asset: Asset
  model: ProductModel | undefined
  hasOpenDamage: boolean
  onApply: (to: AssetStatus, reason: string) => void
  onCancel: () => void
}) {
  const moves = LIFECYCLE[asset.status]
  const [chosen, setChosen] = useState<AssetStatus | ''>('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')

  const move = moves.find((m) => m.to === chosen)
  const needsReason = chosen !== '' && NEEDS_REASON.includes(chosen)
  const leaving = chosen !== '' && LEAVES_THE_FLEET.includes(chosen)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!move) {
      setError('Choose what you want to do with this unit.')
      return
    }
    if (needsReason && reason.trim().length < MIN_REASON_LENGTH) {
      setError('Say why in a few words. It is the only record of the decision.')
      return
    }
    setError('')
    onApply(move.to, reason.trim())
  }

  if (moves.length === 0) {
    return (
      <>
        <EmptyState title="Nothing to change here" body={noMovesReason(asset.status)} />
        <div className="flex justify-center">
          <button type="button" className="btn-secondary px-md" onClick={onCancel}>Close</button>
        </div>
      </>
    )
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-md">
      <p className="flex flex-wrap items-center gap-sm text-sm text-slate-soft">
        <span className="font-mono text-ink">{asset.tag}</span>
        is currently
        <StatusPill status={asset.status} />
      </p>

      <fieldset className="flex flex-col gap-sm">
        <legend className="field-label">What do you want to do</legend>
        {moves.map((option) => {
          const blocked = blockedReason(option, hasOpenDamage)
          const id = `move-${option.to}`
          return (
            /* The whole row is the label, so the 20px radio is never the
               only thing to hit. `choice-row` carries the 44px minimum. */
            <label
              key={option.to}
              htmlFor={id}
              className={`choice-row p-md ${
                blocked ? 'cursor-not-allowed bg-muted hover:bg-muted' : 'bg-surface'
              }`}
            >
              <input
                id={id}
                type="radio"
                name="lifecycle-move"
                value={option.to}
                disabled={blocked !== null}
                checked={chosen === option.to}
                className="mt-1 h-5 w-5 shrink-0 cursor-pointer accent-slate disabled:cursor-not-allowed"
                onChange={() => { setChosen(option.to); setError('') }}
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-ink">{option.label}</span>
                <span className="mt-xs block text-sm text-slate-soft">{option.consequence}</span>
                {blocked && (
                  <span className="mt-xs block text-sm font-medium text-status-due">{blocked}</span>
                )}
              </span>
            </label>
          )
        })}
      </fieldset>

      {leaving && (
        <Notice tone="warn" title="This takes the unit out of the fleet">
          <p>
            {model ? `${model.name} ` : ''}
            leaves the fleet at a replacement value of {money(model?.replacementValue ?? 0)}. It stops
            counting towards utilisation and cannot be hired out again.
          </p>
        </Notice>
      )}

      {needsReason && (
        <Field
          label="Why"
          htmlFor="lifecycle-reason"
          help="This is what the audit log will show, so write it for whoever reads it next."
          error={error || undefined}
        >
          <textarea
            id="lifecycle-reason"
            rows={2}
            className="field-input"
            value={reason}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? 'lifecycle-reason-error' : 'lifecycle-reason-help'}
            onChange={(e) => { setReason(e.target.value); setError('') }}
          />
        </Field>
      )}

      {error && !needsReason && <Notice tone="error" title={error} />}

      <div className="flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          {move ? move.label : 'Apply the change'}
        </button>
        <button type="button" className="btn-secondary px-md" onClick={onCancel}>
          <X className="h-4 w-4 shrink-0" aria-hidden="true" />
          Cancel
        </button>
      </div>
    </form>
  )
}

export type DamageOutcome = 'REPAIRED' | 'WRITE_OFF'

/** Close a damage report with what the repair actually cost. */
export function DamageResolutionPanel({
  report, asset, model, onResolve, onCancel,
}: {
  report: DamageReport
  asset: Asset
  model: ProductModel | undefined
  onResolve: (actualRepairCost: number, outcome: DamageOutcome) => void
  onCancel: () => void
}) {
  const [outcome, setOutcome] = useState<DamageOutcome>('REPAIRED')
  const [cost, setCost] = useState('')
  const [error, setError] = useState('')

  const replacement = model?.replacementValue ?? 0
  const actual = Number(cost)
  const entered = cost.trim() !== '' && !Number.isNaN(actual)
  const difference = entered ? actual - report.estimatedRepairCost : 0

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!entered) {
      setError('Enter what the repair actually cost, in rand. Enter R0.00 if it cost nothing.')
      return
    }
    if (actual < 0) {
      setError('A repair cost cannot be less than zero.')
      return
    }
    if (outcome === 'REPAIRED' && actual > replacement) {
      setError(
        `The repair came to ${money(actual)}, more than the ${money(replacement)} it costs to replace the unit. Write it off instead.`,
      )
      return
    }
    setError('')
    onResolve(actual, outcome)
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-md">
      <div className="rounded border border-line bg-muted p-md">
        <p className="text-sm font-medium text-ink">
          <span className="font-mono">{asset.tag}</span>, {SEVERITY_LABEL[report.severity]} damage
          raised {formatDate(report.raisedAt)}
        </p>
        <p className="mt-xs text-sm text-slate-soft">{report.description}</p>
        <p className="mt-sm text-sm text-slate-soft">
          Estimated at <span className="tabular font-medium text-ink">{money(report.estimatedRepairCost)}</span>.{' '}
          {report.chargeable
            ? 'Chargeable to the customer once the actual cost is known.'
            : 'Carried by the business, not charged to the customer.'}
        </p>
      </div>

      <Field
        label="What the repair actually cost"
        htmlFor="actual-cost"
        help="The workshop invoice figure, in rand."
        error={error || undefined}
      >
        <input
          id="actual-cost"
          type="number"
          min={0}
          step={10}
          inputMode="decimal"
          className="field-input tabular"
          value={cost}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? 'actual-cost-error' : 'actual-cost-help'}
          onChange={(e) => { setCost(e.target.value); setError('') }}
        />
      </Field>

      {entered && difference !== 0 && (
        <p className="text-sm text-slate-soft">
          That is {money(Math.abs(difference))} {difference > 0 ? 'more' : 'less'} than the estimate.
        </p>
      )}

      <fieldset className="flex flex-col gap-sm">
        <legend className="field-label">What happens to the unit</legend>
        {([
          { value: 'REPAIRED' as const, label: 'Repaired, put it back on the shelf', hint: 'The unit goes back into the fleet and customers can hire it again.' },
          { value: 'WRITE_OFF' as const, label: 'Beyond economical repair, write it off', hint: `The unit leaves the fleet at its ${money(replacement)} replacement value.` },
        ]).map((option) => (
          <label
            key={option.value}
            htmlFor={`outcome-${option.value}`}
            className="choice-row bg-surface p-md"
          >
            <input
              id={`outcome-${option.value}`}
              type="radio"
              name="damage-outcome"
              value={option.value}
              checked={outcome === option.value}
              className="mt-1 h-5 w-5 shrink-0 cursor-pointer accent-slate"
              onChange={() => { setOutcome(option.value); setError('') }}
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-ink">{option.label}</span>
              <span className="mt-xs block text-sm text-slate-soft">{option.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <div className="flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          Close this damage report
        </button>
        <button type="button" className="btn-secondary px-md" onClick={onCancel}>
          <X className="h-4 w-4 shrink-0" aria-hidden="true" />
          Cancel
        </button>
      </div>
    </form>
  )
}
