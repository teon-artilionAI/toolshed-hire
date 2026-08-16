/**
 * The parts of the SC-16 damage form that are not plain text boxes.
 *
 * Severity and who pays are radio groups in a real fieldset with a legend
 * rather than dropdowns, because both change what happens next and a counter
 * assistant should be able to read every option at once with one thumb on the
 * screen. Each option carries the consequence of choosing it, not just a word.
 */

import type { DamageReport } from '../../shared/types'
import { AlertCircle, Camera, X } from 'lucide-react'

export type Severity = DamageReport['severity']

const SEVERITIES: { value: Severity; label: string; detail: string }[] = [
  {
    value: 'MINOR',
    label: 'Minor',
    detail: 'Cosmetic or quickly put right. The unit still works and can go out again soon.',
  },
  {
    value: 'MODERATE',
    label: 'Moderate',
    detail: 'Needs workshop time before it can be hired again. Book it in.',
  },
  {
    value: 'SEVERE',
    label: 'Severe',
    detail: 'Unsafe or not worth repairing. The owner decides whether to write it off.',
  },
]

const CHARGE_OPTIONS: { value: boolean; label: string; detail: string }[] = [
  {
    value: true,
    label: 'Charge the customer',
    detail: 'The repair comes off the deposit at the return inspection.',
  },
  {
    value: false,
    label: 'Toolshed Hire absorbs it',
    detail: 'Fair wear and tear, or our own fault. The deposit is released in full.',
  },
]

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null
  return (
    <p className="field-error" id={id}>
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </p>
  )
}

function OptionCard({
  id,
  name,
  checked,
  onSelect,
  label,
  detail,
}: {
  id: string
  name: string
  checked: boolean
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
        onChange={onSelect}
        className="mt-xs h-5 w-5 shrink-0 cursor-pointer accent-accent"
      />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink">{label}</span>
        <span className="mt-xs block text-sm text-slate-soft">{detail}</span>
      </span>
    </label>
  )
}

export function SeverityChoice({
  value,
  onChange,
  error,
}: {
  value: Severity | null
  onChange: (next: Severity) => void
  error?: string
}) {
  return (
    <fieldset
      className="min-w-0"
      aria-describedby={error ? 'severity-error' : undefined}
    >
      <legend className="field-label">How bad is it</legend>
      <div className="mt-xs grid gap-sm sm:grid-cols-3">
        {SEVERITIES.map((option) => (
          <OptionCard
            key={option.value}
            id={`sev-${option.value}`}
            name="severity"
            checked={value === option.value}
            onSelect={() => onChange(option.value)}
            label={option.label}
            detail={option.detail}
          />
        ))}
      </div>
      <FieldError id="severity-error" message={error} />
    </fieldset>
  )
}

export function ChargeableChoice({
  value,
  onChange,
  error,
}: {
  value: boolean | null
  onChange: (next: boolean) => void
  error?: string
}) {
  return (
    <fieldset
      className="min-w-0"
      aria-describedby={error ? 'chargeable-error' : undefined}
    >
      <legend className="field-label">Who pays for the repair</legend>
      <div className="mt-xs grid gap-sm sm:grid-cols-2">
        {CHARGE_OPTIONS.map((option) => (
          <OptionCard
            key={String(option.value)}
            id={`charge-${option.value}`}
            name="chargeable"
            checked={value === option.value}
            onSelect={() => onChange(option.value)}
            label={option.label}
            detail={option.detail}
          />
        ))}
      </div>
      <FieldError id="chargeable-error" message={error} />
    </fieldset>
  )
}

export function PhotographPicker({
  files,
  onChange,
}: {
  files: string[]
  onChange: (next: string[]) => void
}) {
  return (
    <div>
      <span className="field-label">Photographs</span>
      <label
        htmlFor="damage-photos"
        className="flex min-h-[6rem] cursor-pointer flex-col items-center justify-center gap-sm rounded border-2 border-dashed border-line p-lg text-center transition-colors duration-200 hover:border-accent hover:bg-accent-wash"
      >
        <Camera className="h-6 w-6 text-slate-faint" aria-hidden="true" />
        <span className="text-sm font-medium text-ink">
          Take a photograph, or choose one from this device
        </span>
        <span className="text-sm text-slate-soft">
          Two or three shots, close up and from a distance
        </span>
        <input
          id="damage-photos"
          type="file"
          accept="image/*"
          multiple
          className="sr-only"
          onChange={(e) => {
            const chosen = Array.from(e.target.files ?? []).map((f) => f.name)
            onChange([...files, ...chosen])
          }}
        />
      </label>
      <p className="field-help">
        Photographs are not uploaded in this prototype. The file names are kept
        so the flow can be shown end to end.
      </p>
      {files.length > 0 && (
        <ul className="mt-sm flex flex-col gap-sm">
          {files.map((name, index) => (
            <li
              key={`${name}-${index}`}
              className="flex items-center justify-between gap-sm rounded bg-muted px-sm py-xs"
            >
              <span className="min-w-0 truncate text-sm text-ink">{name}</span>
              <button
                type="button"
                className="btn px-sm text-slate-soft hover:bg-surface hover:text-ink"
                onClick={() => onChange(files.filter((_, i) => i !== index))}
              >
                <X className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="sr-only">Remove {name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
