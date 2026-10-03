/**
 * Form controls shared by the counter forms.
 *
 * `Field` in the shared layer draws the label, the help and the error, but it
 * never sees the control, so it cannot tie them to it. These wrappers do, so
 * every input announces its own help and its own error and a screen reader
 * user never has to guess which message belongs to which box.
 *
 * Every control is at least 44 pixels tall, from the shared input style, and
 * a check box carries its whole row as the target.
 */

import type { ChangeEvent, ReactNode, RefObject } from 'react'
import { Field } from '../../shared/ui'

/** The ids `Field` gives its help and its error, for whichever are on screen. */
function describedBy(id: string, help?: string, error?: string): string | undefined {
  const ids = [help ? `${id}-help` : '', error ? `${id}-error` : ''].filter(Boolean).join(' ')
  return ids || undefined
}

interface ControlProps {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  help?: string
  error?: string
  disabled?: boolean
}

export function TextInput({
  id,
  label,
  value,
  onChange,
  help,
  error,
  disabled,
  type = 'text',
  inputMode,
  autoComplete,
  maxLength,
  placeholder,
  inputRef,
}: ControlProps & {
  type?: 'text' | 'tel' | 'search'
  inputMode?: 'text' | 'tel' | 'numeric'
  autoComplete?: string
  maxLength?: number
  placeholder?: string
  inputRef?: RefObject<HTMLInputElement | null>
}) {
  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <input
        ref={inputRef}
        id={id}
        name={id}
        type={type}
        inputMode={inputMode}
        autoComplete={autoComplete}
        maxLength={maxLength}
        placeholder={placeholder}
        disabled={disabled}
        value={value}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        className={`field-input ${error ? 'border-status-overdue' : ''}`}
      />
    </Field>
  )
}

/** A calendar date, `YYYY-MM-DD`, with the earliest day the picker offers. */
export function DateInput({
  id,
  label,
  value,
  onChange,
  help,
  error,
  min,
}: ControlProps & { min: string }) {
  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <input
        id={id}
        name={id}
        type="date"
        min={min}
        value={value}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        className={`field-input cursor-pointer ${error ? 'border-status-overdue' : ''}`}
      />
    </Field>
  )
}

export function SelectInput({
  id,
  label,
  value,
  onChange,
  help,
  error,
  disabled,
  options,
}: ControlProps & { options: readonly { value: string; label: string }[] }) {
  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <select
        id={id}
        name={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        className={`field-input cursor-pointer ${error ? 'border-status-overdue' : ''}`}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  )
}

/** A check box with its whole row as the target, and its error tied to it. */
export function CheckRow({
  id,
  checked,
  onChange,
  error,
  disabled,
  children,
}: {
  id: string
  checked: boolean
  onChange: (checked: boolean) => void
  error?: string
  disabled?: boolean
  children: ReactNode
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className={`choice-row ${error ? 'border-status-overdue' : ''}`}
      >
        <input
          id={id}
          name={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer accent-accent"
        />
        <span className="min-w-0 text-sm text-ink">{children}</span>
      </label>
      {error && (
        <p className="field-error" id={`${id}-error`}>
          <span>{error}</span>
        </p>
      )}
    </div>
  )
}

/**
 * The problems with a form, above it, after a press that was held back. Each
 * one jumps to the field it is about.
 */
export function ProblemList({ problems }: { problems: readonly { id: string; message: string }[] }) {
  if (problems.length === 0) return null
  return (
    <ul className="mt-xs flex flex-col">
      {problems.map((problem) => (
        <li key={problem.id}>
          <a
            href={`#${problem.id}`}
            className="inline-flex min-h-[2.75rem] cursor-pointer items-center underline transition-colors duration-200 hover:text-ink"
          >
            {problem.message}
          </a>
        </li>
      ))}
    </ul>
  )
}
