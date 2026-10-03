/**
 * The choices on SC-16 that are not plain text boxes. How bad the damage is,
 * whether the customer is charged, and how the owner resolved a report. The
 * options of each are in SC16-damage-choices.ts.
 *
 * Each is a radio group in a real fieldset with a legend rather than a
 * dropdown, because each changes what happens next and a counter assistant
 * should be able to read every option at once with one thumb on the screen.
 * Each option carries the consequence of choosing it, not just a word, and the
 * whole option is the target, so it is never smaller than 44 pixels.
 *
 * A group starts with nothing chosen when it is given null. The help and the
 * error of a group are tied to the group, so a screen reader reads them when
 * it enters it. The group itself can take focus, so a problem listed above the
 * form can jump to it.
 */

import { AlertCircle } from 'lucide-react'
import type { ChoiceOption } from './SC16-damage-choices'

function OptionCard({
  id,
  name,
  checked,
  invalid,
  disabled,
  onSelect,
  label,
  detail,
}: {
  id: string
  name: string
  checked: boolean
  invalid: boolean
  disabled: boolean
  onSelect: () => void
  label: string
  detail: string
}) {
  return (
    <label
      htmlFor={id}
      className={`flex min-h-[2.75rem] cursor-pointer items-start gap-sm rounded border p-sm transition-colors duration-200 ${
        checked ? 'border-accent bg-accent-wash' : 'border-line hover:bg-muted'
      }`}
    >
      <input
        id={id}
        type="radio"
        name={name}
        checked={checked}
        disabled={disabled}
        onChange={onSelect}
        aria-invalid={invalid ? true : undefined}
        className="mt-xs h-5 w-5 shrink-0 cursor-pointer accent-accent"
      />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink">{label}</span>
        <span className="mt-xs block text-sm text-slate-soft">{detail}</span>
      </span>
    </label>
  )
}

/**
 * A radio group with a legend, its help and its error tied to it.
 *
 * @param id The id of the group, which a problem listed above the form links to.
 *   Each option's id is built from it.
 */
export function ChoiceGroup<Value extends string>({
  id,
  legend,
  help,
  error,
  options,
  value,
  onChange,
  columns,
  disabled = false,
}: {
  id: string
  legend: string
  help?: string
  error?: string
  options: readonly ChoiceOption<Value>[]
  value: Value | null
  onChange: (next: Value) => void
  /** How many options sit side by side from the `sm` width up. */
  columns: 2 | 3
  disabled?: boolean
}) {
  const describedBy = [help ? `${id}-help` : '', error ? `${id}-error` : ''].filter(Boolean).join(' ')
  return (
    <fieldset id={id} tabIndex={-1} className="min-w-0" aria-describedby={describedBy || undefined}>
      <legend className="field-label">{legend}</legend>
      {help && (
        <p className="field-help mb-xs mt-0" id={`${id}-help`}>
          {help}
        </p>
      )}
      <div className={`mt-xs grid gap-sm ${columns === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}>
        {options.map((option) => (
          <OptionCard
            key={option.value}
            id={`${id}-${option.value}`}
            name={id}
            checked={value === option.value}
            invalid={Boolean(error)}
            disabled={disabled}
            onSelect={() => onChange(option.value)}
            label={option.label}
            detail={option.detail}
          />
        ))}
      </div>
      {error && (
        <p className="field-error" id={`${id}-error`}>
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </fieldset>
  )
}
