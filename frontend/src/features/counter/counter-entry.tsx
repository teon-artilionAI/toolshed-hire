/**
 * One thing on the counter's day, drawn as a block of its own.
 *
 * The dashboard and the diary both list bookings that go out and hires that
 * come back, and both draw each one the same way. It is an item in a real list
 * and not a row of columns, so a phone held at the counter never has to scroll
 * sideways. The reference and the status come first, then who it is for and
 * how to reach them, then what it is. The way to deal with it sits on the
 * right on a wide screen and wraps underneath on a phone.
 *
 * Every link names the booking or the hire it opens for a screen reader, so a
 * list of "Check out" links can be told apart without reading the rows.
 */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

export function CounterEntry({
  reference,
  status,
  customerName,
  customerPhone,
  children,
  actions,
  footer,
}: {
  reference: string
  /** The status pill, when the entry has a status to show. */
  status?: ReactNode
  customerName: string
  customerPhone: string
  /** The lines that say what it is, each one a paragraph. */
  children: ReactNode
  /** The links that deal with it. */
  actions?: ReactNode
  /** Anything that needs the whole width, such as a question to answer. */
  footer?: ReactNode
}) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-md border-t border-line py-md first:border-t-0 first:pt-0">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-sm">
          <span className="font-mono text-sm font-medium text-ink">{reference}</span>
          {status}
        </p>
        <p className="mt-xs break-words font-medium text-ink">{customerName}</p>
        <p className="tabular text-sm text-slate-soft">{customerPhone}</p>
        <div className="mt-xs flex flex-col gap-xs break-words text-sm text-ink">{children}</div>
      </div>
      {actions && <div className="flex flex-wrap gap-sm empty:hidden">{actions}</div>}
      {/* A footer that draws nothing leaves its box empty, and an empty box
          takes no room, so the entry does not grow a gap underneath. */}
      {footer && <div className="w-full empty:hidden">{footer}</div>}
    </li>
  )
}

/** A link that deals with one entry. The reference is read out after the words. */
export function EntryLink({
  to,
  reference,
  primary = false,
  children,
}: {
  to: string
  reference: string
  primary?: boolean
  children: string
}) {
  return (
    <Link to={to} className={`${primary ? 'btn-primary' : 'btn-secondary'} px-md`}>
      {children} <span className="sr-only">{reference}</span>
    </Link>
  )
}

/** A link in the heading of a card, to the screen that shows more. */
export function CardLink({ to, children }: { to: string; children: string }) {
  return (
    <Link to={to} className="btn-ghost px-sm text-sm">
      {children}
      <ArrowRight className="h-4 w-4" aria-hidden="true" />
    </Link>
  )
}
