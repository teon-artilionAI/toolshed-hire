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
 */

import { useState } from 'react'
import type { ReactNode } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { Field } from '../../shared/ui'

export const MIN_PASSWORD_LENGTH = 10

/** Strip the spaces and dashes people type into phone and ID numbers. */
export function stripSeparators(value: string): string {
  return value.replace(/[\s-]/g, '')
}

export function isEmailWellFormed(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim())
}

/** Ten digits starting with a zero, which is how South Africans write a
 *  mobile number. Spaces and dashes are forgiven. */
export function isMobileWellFormed(value: string): boolean {
  return /^0\d{9}$/.test(stripSeparators(value))
}

export function isThirteenDigits(value: string): boolean {
  return /^\d{13}$/.test(stripSeparators(value))
}

/** Returns the problem with a password, or undefined when it is fine. */
export function passwordProblem(value: string): string | undefined {
  if (!value.trim()) return 'Choose a password so you can sign in again later.'
  if (value.length < MIN_PASSWORD_LENGTH) {
    return `Passwords need at least ${MIN_PASSWORD_LENGTH} characters. Yours has ${value.length}.`
  }
  if (!/\d/.test(value)) return 'Add at least one number to your password.'
  return undefined
}

/** The ids `Field` gives its help and error paragraphs, so a control can
 *  point at whichever of them is on screen. */
export function describedBy(
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
}: ControlProps & {
  type?: 'text' | 'email' | 'tel'
  inputMode?: 'text' | 'email' | 'tel' | 'numeric'
  placeholder?: string
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
}: ControlProps & { options: { value: string; label: string }[] }) {
  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <select
        id={id}
        name={id}
        value={value}
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
