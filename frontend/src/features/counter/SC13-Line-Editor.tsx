/**
 * One line of a booking, for SC-13.
 *
 * The conflict case lives here. When a unit is already spoken for, the
 * screen says which booking has it and until when, and then offers the
 * three answers a counter assistant would give out loud: another unit,
 * another branch, or different dates. Nothing is hidden behind a generic
 * "not available".
 */

import { Trash2 } from 'lucide-react'
import { Field, Notice, StatusPill } from '../../shared/ui'
import { productModels } from '../../shared/fixtures'
import { daysBetween, formatDate, money } from '../../shared/format'
import type { BranchCode } from '../../shared/types'
import { modelById } from './counter-desk-data'
import type { BookingLineDraft, LineAllocation, UnitState } from './counter-availability'
import { branchAvailability, nextFreePeriod, unitStateSummary } from './counter-availability'

/** Every unit shows a label as well as a colour, so the state survives
 *  greyscale and colour blindness. */
const PILL: Record<UnitState['kind'], { status: string; label: string }> = {
  free: { status: 'AVAILABLE', label: 'Free' },
  'out-of-service': { status: 'QUARANTINED', label: 'Not hireable' },
  'still-out': { status: 'ON_HIRE', label: 'Still out' },
  clash: { status: 'RESERVED', label: 'Spoken for' },
}

export default function LineEditor({
  line,
  position,
  branch,
  startDate,
  endDate,
  allocation,
  onChange,
  onRemove,
  onMoveBranch,
  onShiftPeriod,
}: {
  line: BookingLineDraft
  position: number
  branch: BranchCode
  startDate: string
  endDate: string
  allocation: LineAllocation
  onChange: (line: BookingLineDraft) => void
  onRemove: () => void
  onMoveBranch: (code: BranchCode) => void
  onShiftPeriod: (start: string, end: string) => void
}) {
  const model = modelById(line.modelId)
  const days = Math.max(1, daysBetween(startDate, endDate))
  const hire = model.dailyRate * days * line.quantity
  const deposit = model.depositAmount * line.quantity
  const modeName = `line-${line.id}-mode`

  function toggleUnit(assetId: string) {
    const picked = line.assetIds.includes(assetId)
      ? line.assetIds.filter((id) => id !== assetId)
      : [...line.assetIds, assetId]
    onChange({ ...line, mode: 'MANUAL', assetIds: picked })
  }

  /** Swap the line onto a unit that is free, keeping any good picks. */
  function swapOnto(assetId: string) {
    const keep = allocation.chosen
      .filter((u) => u.state.kind === 'free')
      .map((u) => u.asset.id)
      .filter((id) => id !== assetId)
    onChange({
      ...line,
      mode: 'MANUAL',
      assetIds: [...keep, assetId].slice(-line.quantity),
    })
  }

  const elsewhere = branchAvailability(line.modelId, startDate, endDate).filter(
    (option) => option.branch.code !== branch,
  )
  const blockedUnit = allocation.blocked[0]?.asset ?? allocation.units[0]?.asset
  const shift = blockedUnit ? nextFreePeriod(blockedUnit, startDate, endDate) : undefined
  const alternatives = allocation.free.filter(
    (asset) => !allocation.chosen.some((u) => u.asset.id === asset.id),
  )

  return (
    <li className="card p-lg">
      <div className="mb-md flex flex-wrap items-end gap-md">
        <div className="min-w-[16rem] flex-1">
          <Field label={`Tool ${position}`} htmlFor={`line-${line.id}-model`}>
            <select
              id={`line-${line.id}-model`}
              className="field-input cursor-pointer"
              value={line.modelId}
              onChange={(event) =>
                onChange({ ...line, modelId: event.target.value, assetIds: [] })
              }
            >
              {productModels.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.manufacturer} {option.name}
                  {option.published ? '' : ' (not on the website)'}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="w-28">
          <Field label="How many" htmlFor={`line-${line.id}-qty`}>
            <input
              id={`line-${line.id}-qty`}
              type="number"
              min={1}
              max={5}
              className="field-input tabular"
              value={line.quantity}
              onChange={(event) =>
                onChange({
                  ...line,
                  quantity: Math.min(5, Math.max(1, Number(event.target.value) || 1)),
                })
              }
            />
          </Field>
        </div>

        <button type="button" onClick={onRemove} className="btn-secondary">
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          Remove
        </button>
      </div>

      <fieldset className="mb-md">
        <legend className="field-label">Which unit goes out</legend>
        <div className="flex flex-wrap gap-sm">
          {(['AUTO', 'MANUAL'] as const).map((mode) => (
            <label
              key={mode}
              className="flex min-h-[2.75rem] cursor-pointer items-center gap-sm rounded border border-line px-md py-sm text-sm transition-colors duration-200 hover:bg-muted"
            >
              <input
                type="radio"
                name={modeName}
                className="h-5 w-5 cursor-pointer"
                checked={line.mode === mode}
                onChange={() => onChange({ ...line, mode, assetIds: [] })}
              />
              {mode === 'AUTO' ? 'Let the system pick' : 'Choose the unit myself'}
            </label>
          ))}
        </div>
      </fieldset>

      {line.mode === 'MANUAL' ? (
        <fieldset className="mb-md">
          <legend className="field-label">
            Units at this branch, {line.assetIds.length} of {line.quantity} picked
          </legend>
          {allocation.units.length === 0 ? (
            <p className="text-sm text-slate-soft">
              This branch does not carry {model.name}. Try another branch below.
            </p>
          ) : (
            <ul className="flex flex-col gap-sm">
              {allocation.units.map(({ asset, state }) => (
                <li key={asset.id}>
                  <label className="flex min-h-[2.75rem] cursor-pointer flex-wrap items-center gap-sm rounded border border-line px-md py-sm transition-colors duration-200 hover:bg-muted">
                    <input
                      type="checkbox"
                      className="h-5 w-5 cursor-pointer"
                      checked={line.assetIds.includes(asset.id)}
                      onChange={() => toggleUnit(asset.id)}
                    />
                    <span className="font-mono text-sm text-ink">{asset.tag}</span>
                    <StatusPill status={PILL[state.kind].status} label={PILL[state.kind].label} />
                    <span className="text-sm text-slate-soft">{unitStateSummary(state)}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </fieldset>
      ) : (
        <p className="mb-md text-sm text-slate-soft">
          {allocation.chosen.length > 0
            ? `Set aside: ${allocation.chosen.map((u) => u.asset.tag).join(', ')}.`
            : 'Nothing of this model is free at this branch for these dates.'}
        </p>
      )}

      {allocation.problem && (
        <div className="mb-md">
          <Notice tone="error" title={allocation.problem}>
            <ul className="mb-sm flex flex-col gap-xs">
              {allocation.blocked.map(({ asset, state }) => (
                <li key={asset.id}>
                  <span className="font-mono">{asset.tag}</span>: {unitStateSummary(state)}
                </li>
              ))}
            </ul>
            <p className="font-medium">Three ways to fix this.</p>

            <div className="mt-sm flex flex-col gap-sm">
              <div>
                <p className="text-sm">1. Another unit at this branch</p>
                {alternatives.length === 0 ? (
                  <p className="text-sm text-slate-soft">
                    Nothing else of this model is free here for these dates.
                  </p>
                ) : (
                  <div className="mt-xs flex flex-wrap gap-sm">
                    {alternatives.map((asset) => (
                      <button
                        key={asset.id}
                        type="button"
                        onClick={() => swapOnto(asset.id)}
                        className="btn-secondary font-mono"
                      >
                        Use {asset.tag}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <p className="text-sm">2. Another branch</p>
                <div className="mt-xs flex flex-wrap gap-sm">
                  {elsewhere.map((option) => (
                    <button
                      key={option.branch.code}
                      type="button"
                      disabled={option.free.length < line.quantity}
                      onClick={() => onMoveBranch(option.branch.code)}
                      className="btn-secondary"
                    >
                      {option.branch.name}, {option.free.length} free
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <p className="text-sm">3. Different dates</p>
                {shift ? (
                  <button
                    type="button"
                    onClick={() => onShiftPeriod(shift.startDate, shift.endDate)}
                    className="btn-secondary mt-xs"
                  >
                    Shift to {formatDate(shift.startDate)} to {formatDate(shift.endDate)}
                  </button>
                ) : (
                  <p className="text-sm text-slate-soft">
                    No later date frees this unit within the next few weeks.
                  </p>
                )}
              </div>
            </div>
          </Notice>
        </div>
      )}

      <p className="tabular text-sm text-slate-soft">
        {line.quantity} x {days} {days === 1 ? 'day' : 'days'} at {money(model.dailyRate)} a day is{' '}
        <span className="font-medium text-ink">{money(hire)}</span>, plus {money(deposit)} deposit
        held.
      </p>
    </li>
  )
}
