/**
 * Form controls shared by the customer screens.
 *
 * `Field` in the shared layer draws the label, help text and error, but it
 * cannot wire the control's `aria-describedby` because it never sees the
 * control. These wrappers close that gap, so every input on a customer form
 * announces its own help text and its own error rather than leaving a
 * screen reader user to guess which message belongs to which box.
 *
 * The reveal toggle lives here too. It is a 44 by 44 target inside the
 * field, which is what a thumb needs on a phone at a counter.
 *
 * The checks a form runs on what was typed are in customer-rules.ts.
 */

import { useState } from 'react'
import type { ReactNode } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { Field } from '../../shared/ui'

/** The ids `Field` gives its help and error paragraphs, so a control can
 *  point at whichever of them is on screen. */
function describedBy(
  id: string,
  hasHelp: boolean,
  hasError: boolean,
): string | undefined {
  const ids = [hasHelp ? `${id}-help` : '', hasError ? `${id}-error` : '']
    .filter(Boolean)
    .join(' ')
  return ids || undefined
}

interface ControlProps {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  help?: string
  error?: string
  required?: boolean
  autoComplete?: string
}

export function TextField({
  id,
  label,
  value,
  onChange,
  onBlur,
  help,
  error,
  required,
  autoComplete,
  type = 'text',
  inputMode,
  placeholder,
  maxLength,
  disabled,
}: ControlProps & {
  type?: 'text' | 'email' | 'tel'
  inputMode?: 'text' | 'email' | 'tel' | 'numeric'
  placeholder?: string
  /** The most characters the box takes. */
  maxLength?: number
  disabled?: boolean
}) {
  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <input
        id={id}
        name={id}
        type={type}
        inputMode={inputMode}
        placeholder={placeholder}
        autoComplete={autoComplete}
        required={required}
        maxLength={maxLength}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, Boolean(help), Boolean(error))}
        className={`field-input ${error ? 'border-status-overdue' : ''}`}
      />
    </Field>
  )
}

export function SelectField({
  id,
  label,
  value,
  onChange,
  onBlur,
  help,
  error,
  options,
  disabled,
}: ControlProps & { options: { value: string; label: string }[]; disabled?: boolean }) {
  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <select
        id={id}
        name={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, Boolean(help), Boolean(error))}
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

export function PasswordField({
  id,
  label,
  value,
  onChange,
  onBlur,
  help,
  error,
  autoComplete = 'current-password',
}: ControlProps) {
  const [revealed, setRevealed] = useState(false)
  const Icon = revealed ? EyeOff : Eye

  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <div className="relative">
        <input
          id={id}
          name={id}
          type={revealed ? 'text' : 'password'}
          autoComplete={autoComplete}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, Boolean(help), Boolean(error))}
          className={`field-input pr-[3.25rem] ${error ? 'border-status-overdue' : ''}`}
        />
        <button
          type="button"
          onClick={() => setRevealed((current) => !current)}
          aria-pressed={revealed}
          className="absolute right-0 top-0 flex h-11 w-11 cursor-pointer items-center
                     justify-center rounded text-slate-soft transition-colors
                     duration-200 hover:bg-muted hover:text-ink"
        >
          <Icon className="h-5 w-5" aria-hidden="true" />
          <span className="sr-only">
            {revealed ? 'Hide password' : 'Show password'}
          </span>
        </button>
      </div>
    </Field>
  )
}

export function CheckboxField({
  id,
  checked,
  onChange,
  error,
  children,
}: {
  id: string
  checked: boolean
  onChange: (checked: boolean) => void
  error?: string
  children: ReactNode
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="flex min-h-[2.75rem] cursor-pointer items-start gap-sm py-sm text-sm text-ink"
      >
        <input
          id={id}
          name={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer rounded border-line accent-accent"
        />
        <span>{children}</span>
      </label>
      {error && (
        <p className="field-error" id={`${id}-error`}>
          <span>{error}</span>
        </p>
      )}
    </div>
  )
}

/** The list of problems shown above a form after a failed submit. Each row
 *  jumps to the field it is about, which is the fastest way through a long
 *  form on a phone. */
export function ErrorSummary({
  problems,
}: {
  problems: { id: string; message: string }[]
}) {
  if (problems.length === 0) return null
  return (
    <ul className="mt-xs flex flex-col">
      {problems.map((problem) => (
        <li key={problem.id}>
          <a
            href={`#${problem.id}`}
            className="inline-flex min-h-[2.75rem] cursor-pointer items-center
                       underline transition-colors duration-200 hover:text-ink"
          >
            {problem.message}
          </a>
        </li>
      ))}
    </ul>
  )
}
