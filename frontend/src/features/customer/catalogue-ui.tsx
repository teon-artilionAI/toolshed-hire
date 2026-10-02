/**
 * Pieces shared by the four customer catalogue screens, SC-01 to SC-04.
 *
 * They live here rather than in `shared/ui` because nothing outside the
 * customer flow needs them, and rather than in one screen because the
 * period picker and the availability chip have to read identically on the
 * home page, the search results and the basket. A customer who sees "free at
 * Bellville" in three different wordings stops believing any of them.
 *
 * Nothing here fetches or imports data. Each piece is handed what it shows, so
 * the screens on the API pass what the API sent and the basket passes its
 * fixtures until it moves over.
 *
 * A model may arrive without a photograph, so the banner always draws a plain
 * gradient and lays the photograph over it when there is one. The name sits on
 * a solid scrim in both cases, because white text straight on an image would
 * fail contrast.
 */

import type { ChangeEvent } from 'react'
import { Ban, CircleCheck, Minus, Plus } from 'lucide-react'
import { Field } from '../../shared/ui'
import { MAX_HIRE_DAYS } from './hire-period'

/** The value a branch filter holds when no branch has been chosen. */
export const ANY_BRANCH = 'ALL'

/**
 * The stand-in for photography, with the model name on a scrim. The image is
 * decorative, so it is hidden from assistive technology. The name is real
 * text and is read normally.
 */
export function ModelBanner({
  name,
  manufacturer,
  imagePath,
  height = 'h-32',
}: {
  name: string
  manufacturer: string
  /** Same origin path to the photograph, or null when there is none. */
  imagePath: string | null
  height?: string
}) {
  return (
    <div
      className={`relative flex ${height} items-end overflow-hidden rounded-t-lg bg-gradient-to-br from-slate-600 to-slate-800`}
    >
      {imagePath && (
        <img
          src={imagePath}
          alt=""
          loading="lazy"
          className="absolute inset-0 h-full w-full object-cover"
        />
      )}
      <div className="relative w-full bg-ink/80 px-md py-sm">
        <p className="text-sm font-semibold leading-tight text-white">{name}</p>
        <p className="mt-xs font-mono text-xs text-white/80">{manufacturer}</p>
      </div>
    </div>
  )
}

/**
 * Whether one branch can supply the tool for the dates asked about. It says
 * free or not free and never how many, because the API does not tell a
 * customer the count. Never colour alone. The words are always present and an
 * icon backs them up.
 */
export function AvailabilityChip({
  branchName,
  available,
}: {
  branchName: string
  available: boolean
}) {
  const Icon = available ? CircleCheck : Ban
  return (
    <span
      className={`pill ${
        available
          ? 'bg-status-available-wash text-status-available'
          : 'bg-status-overdue-wash text-status-overdue'
      }`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>
        {branchName}: {available ? 'Free' : 'Not free'}
      </span>
    </span>
  )
}

/**
 * Collection and return dates. Used on every screen in this flow, always
 * with real labels tied to the inputs. Each date carries its own message, so
 * a refusal from the API lands under the field it is about.
 */
export function PeriodFields({
  idPrefix,
  startIso,
  endIso,
  minIso,
  maxDays = MAX_HIRE_DAYS,
  onChangeStart,
  onChangeEnd,
  startError,
  endError,
}: {
  idPrefix: string
  startIso: string
  endIso: string
  /** The earliest collection date the picker offers, as `YYYY-MM-DD`. */
  minIso: string
  /** The longest hire, used in the help text. */
  maxDays?: number
  onChangeStart: (value: string) => void
  onChangeEnd: (value: string) => void
  startError?: string
  endError?: string
}) {
  const startId = `${idPrefix}-from`
  const endId = `${idPrefix}-to`
  const read = (fn: (value: string) => void) => (e: ChangeEvent<HTMLInputElement>) =>
    fn(e.target.value)

  return (
    <>
      <Field label="Collect on" htmlFor={startId} error={startError}>
        <input
          id={startId}
          type="date"
          className="field-input cursor-pointer"
          value={startIso}
          min={minIso}
          aria-invalid={startError ? true : undefined}
          aria-describedby={startError ? `${startId}-error` : undefined}
          onChange={read(onChangeStart)}
        />
      </Field>
      <Field
        label="Bring back on"
        htmlFor={endId}
        help={`Up to ${maxDays} days. You are charged to the morning you return it.`}
        error={endError}
      >
        <input
          id={endId}
          type="date"
          className="field-input cursor-pointer"
          value={endIso}
          min={startIso}
          aria-invalid={endError ? true : undefined}
          aria-describedby={endError ? `${endId}-help ${endId}-error` : `${endId}-help`}
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

/** What the branch chooser needs to know about a branch. */
export interface BranchOption<Code extends string = string> {
  code: Code
  name: string
}

/**
 * Branch chooser. `allLabel` turns it into an optional filter.
 *
 * The value can come from an address bar, so it may name a branch the list
 * does not hold, or the list may still be on its way. Either way the control
 * shows an option for the value it was given and never quietly shows a
 * different branch from the one in force.
 */
export function BranchSelect<Code extends string>({
  id,
  label = 'Collect from',
  branches,
  value,
  onChange,
  allLabel,
  placeholder = 'Loading branches',
  help,
  error,
}: {
  id: string
  label?: string
  branches: readonly BranchOption<Code>[]
  value: Code | typeof ANY_BRANCH | ''
  onChange: (value: Code | typeof ANY_BRANCH) => void
  allLabel?: string
  /** Shown as the only option while there are no branches to offer. */
  placeholder?: string
  help?: string
  error?: string
}) {
  const known = value === ANY_BRANCH || branches.some((branch) => branch.code === value)
  const describedBy = [help ? `${id}-help` : '', error ? `${id}-error` : ''].join(' ').trim()
  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <select
        id={id}
        className="field-input cursor-pointer"
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        onChange={(e) => {
          const chosen = branches.find((branch) => branch.code === e.target.value)
          onChange(chosen ? chosen.code : ANY_BRANCH)
        }}
      >
        {allLabel && <option value={ANY_BRANCH}>{allLabel}</option>}
        {!allLabel && value === '' && <option value="">{placeholder}</option>}
        {!known && value !== '' && <option value={value}>Chosen branch</option>}
        {branches.map((branch) => (
          <option key={branch.code} value={branch.code}>
            {branch.name}
          </option>
        ))}
      </select>
    </Field>
  )
}
