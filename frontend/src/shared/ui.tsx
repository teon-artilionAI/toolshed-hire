/**
 * Shared interface primitives.
 *
 * Two rules from the brand override are enforced here rather than left to
 * each screen to remember.
 *
 * 1. Status colour never appears on a button. `StatusPill` is the only
 *    component that uses the status scale.
 * 2. Colour is never the sole carrier of meaning. Every pill renders a
 *    label, and a dot as a secondary cue, so the state survives greyscale
 *    printing and colour blindness.
 */

import type { ReactNode } from 'react'
import { AlertCircle, Inbox } from 'lucide-react'
import type {
  AssetStatus,
  DamageStatus,
  RentalStatus,
  ReservationStatus,
} from './types'
import { humanise } from './format'

type StatusTone = 'available' | 'onhire' | 'due' | 'overdue' | 'inactive'

const TONE_CLASS: Record<StatusTone, string> = {
  available: 'bg-status-available-wash text-status-available',
  onhire: 'bg-status-onhire-wash text-status-onhire',
  due: 'bg-status-due-wash text-status-due',
  overdue: 'bg-status-overdue-wash text-status-overdue',
  inactive: 'bg-status-inactive-wash text-status-inactive',
}

const TONE_DOT: Record<StatusTone, string> = {
  available: 'bg-status-available',
  onhire: 'bg-status-onhire',
  due: 'bg-status-due',
  overdue: 'bg-status-overdue',
  inactive: 'bg-status-inactive',
}

const STATUS_TONE: Record<string, StatusTone> = {
  // Assets
  AVAILABLE: 'available',
  RESERVED: 'due',
  ON_HIRE: 'onhire',
  QUARANTINED: 'overdue',
  MAINTENANCE: 'due',
  RETIRED: 'inactive',
  LOST: 'overdue',
  // Reservations
  DRAFT: 'inactive',
  HELD: 'due',
  CONFIRMED: 'onhire',
  COLLECTED: 'onhire',
  CLOSED: 'available',
  CANCELLED: 'inactive',
  NO_SHOW: 'overdue',
  EXPIRED: 'inactive',
  // Rentals
  OPEN: 'onhire',
  OVERDUE: 'overdue',
  PARTIALLY_RETURNED: 'due',
  RETURNED: 'available',
  SETTLED: 'available',
  // Damage
  UNDER_REPAIR: 'due',
  RESOLVED: 'available',
}

export function StatusPill({
  status,
  label,
}: {
  status: AssetStatus | ReservationStatus | RentalStatus | DamageStatus | string
  label?: string
}) {
  const tone = STATUS_TONE[status] ?? 'inactive'
  return (
    <span className={`pill ${TONE_CLASS[tone]}`}>
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[tone]}`}
      />
      {label ?? humanise(status)}
    </span>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
  screenId,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
  /** The SC- identifier from the journey map, shown so the prototype and
   *  the documented screen inventory can be reconciled one to one. */
  screenId?: string
}) {
  return (
    <header className="mb-lg flex flex-wrap items-start justify-between gap-md">
      <div className="min-w-0">
        {screenId && (
          <p className="mb-xs font-mono text-xs uppercase tracking-wide text-slate-faint">
            {screenId}
          </p>
        )}
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        {subtitle && (
          <p className="mt-xs max-w-2xl text-sm text-slate-soft">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap gap-sm">{actions}</div>}
    </header>
  )
}

export function Card({
  title,
  action,
  children,
  className = '',
}: {
  title?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-md border-b border-line px-lg py-md">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-soft">
            {title}
          </h2>
          {action}
        </div>
      )}
      <div className="p-lg">{children}</div>
    </section>
  )
}

export function StatTile({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string
  value: string | number
  hint?: string
  tone?: 'default' | 'warn' | 'bad' | 'good'
}) {
  const toneClass = {
    default: 'text-ink',
    good: 'text-status-available',
    warn: 'text-status-due',
    bad: 'text-status-overdue',
  }[tone]
  return (
    <div className="card p-lg">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-soft">
        {label}
      </p>
      <p className={`tabular mt-sm text-3xl font-semibold ${toneClass}`}>
        {value}
      </p>
      {hint && <p className="mt-xs text-sm text-slate-soft">{hint}</p>}
    </div>
  )
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center px-lg py-2xl text-center">
      <Inbox className="mb-md h-8 w-8 text-slate-faint" aria-hidden="true" />
      <p className="text-base font-medium text-ink">{title}</p>
      <p className="mt-xs max-w-sm text-sm text-slate-soft">{body}</p>
      {action && <div className="mt-lg">{action}</div>}
    </div>
  )
}

/** Inline notice. Errors say what went wrong and what to do about it. */
export function Notice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warn' | 'error' | 'success'
  title: string
  children?: ReactNode
}) {
  const toneClass = {
    info: 'border-status-onhire bg-status-onhire-wash text-status-onhire',
    warn: 'border-status-due bg-status-due-wash text-status-due',
    error: 'border-status-overdue bg-status-overdue-wash text-status-overdue',
    success:
      'border-status-available bg-status-available-wash text-status-available',
  }[tone]
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`flex items-start gap-sm rounded border-l-4 px-md py-sm ${toneClass}`}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <p className="text-sm font-semibold">{title}</p>
        {children && <div className="mt-xs text-sm text-ink">{children}</div>}
      </div>
    </div>
  )
}

export function Field({
  label,
  htmlFor,
  help,
  error,
  children,
}: {
  label: string
  htmlFor: string
  help?: string
  error?: string
  children: ReactNode
}) {
  const helpId = help ? `${htmlFor}-help` : undefined
  const errorId = error ? `${htmlFor}-error` : undefined
  return (
    <div>
      <label className="field-label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {help && (
        <p className="field-help" id={helpId}>
          {help}
        </p>
      )}
      {error && (
        <p className="field-error" id={errorId}>
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </div>
  )
}

export function DataTable({
  columns,
  children,
  caption,
}: {
  columns: string[]
  children: ReactNode
  caption?: string
}) {
  return (
    <div className="table-wrap">
      <table className="w-full border-collapse">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="border-b border-line bg-muted">
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col" className="th">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  )
}
