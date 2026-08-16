/**
 * Pieces shared by the four customer catalogue screens, SC-01 to SC-04.
 *
 * They live here rather than in `shared/ui` because nothing outside the
 * customer flow needs them, and rather than in one screen because the
 * period picker and the availability chip have to read identically on the
 * home page, the search results and the basket. A customer who sees "2
 * free at Bellville" in three different wordings stops believing any of
 * them.
 *
 * There is no photography in the prototype, so each model carries an
 * `imageTone` gradient as its stand-in. The name always sits on a solid
 * scrim rather than on the gradient itself, because white text over the
 * lighter tones would fail contrast.
 */

import type { ChangeEvent } from 'react'
import { Ban, CircleCheck, Minus, Plus, TriangleAlert } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { TODAY, branches } from '../../shared/fixtures'
import type { BranchCode, ProductModel } from '../../shared/types'
import { Field } from '../../shared/ui'
import type { BranchAvailability } from './availability'
import { MAX_HIRE_DAYS } from './hire-period'

/**
 * The gradient stand-in for photography, with the model name on a scrim.
 * Decorative, so it is hidden from assistive technology; the name is real
 * text and is read normally.
 */
export function ModelBanner({
  model,
  height = 'h-32',
}: {
  model: ProductModel
  height?: string
}) {
  return (
    <div
      className={`relative flex ${height} items-end overflow-hidden rounded-t-lg bg-gradient-to-br ${model.imageTone}`}
    >
      <div className="w-full bg-ink/80 px-md py-sm">
        <p className="text-sm font-semibold leading-tight text-white">
          {model.name}
        </p>
        <p className="mt-xs font-mono text-xs text-white/80">
          {model.manufacturer}
        </p>
      </div>
    </div>
  )
}

type ChipTone = 'free' | 'tight' | 'none'

const CHIP_CLASS: Record<ChipTone, string> = {
  free: 'bg-status-available-wash text-status-available',
  tight: 'bg-status-due-wash text-status-due',
  none: 'bg-status-overdue-wash text-status-overdue',
}

const CHIP_ICON: Record<ChipTone, LucideIcon> = {
  free: CircleCheck,
  tight: TriangleAlert,
  none: Ban,
}

function chipToneFor(available: number, wanted: number): ChipTone {
  if (available <= 0) return 'none'
  return available < wanted ? 'tight' : 'free'
}

/**
 * How many units are free at one branch. Never colour alone: the count and
 * a word are always present, and an icon backs them up.
 */
export function AvailabilityChip({
  row,
  wanted = 1,
}: {
  row: BranchAvailability
  wanted?: number
}) {
  const tone = chipToneFor(row.availableUnits, wanted)
  const Icon = CHIP_ICON[tone]
  const label =
    row.fleetUnits === 0
      ? 'Not kept here'
      : row.availableUnits === 0
        ? 'None free'
        : `${row.availableUnits} free`
  return (
    <span className={`pill ${CHIP_CLASS[tone]}`}>
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="tabular">
        {row.branch.name}: {label}
      </span>
    </span>
  )
}

/**
 * Collection and return dates. Used on every screen in this flow, always
 * with real labels tied to the inputs and a single shared error message.
 */
export function PeriodFields({
  idPrefix,
  startIso,
  endIso,
  onChangeStart,
  onChangeEnd,
  error,
}: {
  idPrefix: string
  startIso: string
  endIso: string
  onChangeStart: (value: string) => void
  onChangeEnd: (value: string) => void
  error?: string | null
}) {
  const startId = `${idPrefix}-from`
  const endId = `${idPrefix}-to`
  const read = (fn: (value: string) => void) => (e: ChangeEvent<HTMLInputElement>) =>
    fn(e.target.value)

  return (
    <>
      <Field label="Collect on" htmlFor={startId} error={error ?? undefined}>
        <input
          id={startId}
          type="date"
          className="field-input cursor-pointer"
          value={startIso}
          min={TODAY}
          onChange={read(onChangeStart)}
        />
      </Field>
      <Field
        label="Bring back on"
        htmlFor={endId}
        help={`Up to ${MAX_HIRE_DAYS} days. You are charged to the morning you return it.`}
      >
        <input
          id={endId}
          type="date"
          className="field-input cursor-pointer"
          value={endIso}
          min={startIso}
          onChange={read(onChangeEnd)}
        />
      </Field>
    </>
  )
}

/**
 * How many of a model to hire. Steppers rather than a bare number field,
 * because this is used one handed on a phone at a counter. Both buttons
 * are a full 44 by 44 with 8px between them.
 */
export function QuantityStepper({
  id,
  itemLabel,
  value,
  max,
  onChange,
  min = 1,
}: {
  id: string
  /** What is being counted, so each stepper on a page reads differently
   *  to a screen reader. */
  itemLabel: string
  value: number
  max: number
  onChange: (next: number) => void
  min?: number
}) {
  const clamp = (next: number) => onChange(Math.min(Math.max(min, next), Math.max(min, max)))
  return (
    <div>
      <label className="field-label" htmlFor={id}>
        How many
      </label>
      <div className="flex items-center gap-sm">
        <button
          type="button"
          className="btn-secondary w-11 shrink-0 px-0"
          onClick={() => clamp(value - 1)}
          disabled={value <= min}
        >
          <Minus className="h-4 w-4" aria-hidden="true" />
          <span className="sr-only">One fewer {itemLabel}</span>
        </button>
        <input
          id={id}
          type="number"
          inputMode="numeric"
          className="field-input tabular w-20 text-center"
          value={value}
          min={min}
          max={max}
          onChange={(e) => clamp(Number.parseInt(e.target.value, 10) || min)}
        />
        <button
          type="button"
          className="btn-secondary w-11 shrink-0 px-0"
          onClick={() => clamp(value + 1)}
          disabled={value >= max}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span className="sr-only">One more {itemLabel}</span>
        </button>
      </div>
    </div>
  )
}

/** Branch chooser. `allLabel` turns it into an optional filter. */
export function BranchSelect({
  id,
  label = 'Collect from',
  value,
  onChange,
  allLabel,
}: {
  id: string
  label?: string
  value: BranchCode | 'ALL'
  onChange: (value: BranchCode | 'ALL') => void
  allLabel?: string
}) {
  return (
    <Field label={label} htmlFor={id}>
      <select
        id={id}
        className="field-input cursor-pointer"
        value={value}
        onChange={(e) => onChange(e.target.value as BranchCode | 'ALL')}
      >
        {allLabel && <option value="ALL">{allLabel}</option>}
        {branches.map((b) => (
          <option key={b.code} value={b.code}>
            {b.name}
          </option>
        ))}
      </select>
    </Field>
  )
}
