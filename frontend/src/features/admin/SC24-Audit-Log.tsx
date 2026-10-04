/**
 * SC-24, Audit and notification log.
 *
 * Two records that only make sense side by side. The audit trail says what
 * the business did, and the notification log says whether the customer ever
 * heard about it. When somebody arrives insisting they were never told, the
 * answer is on this screen.
 *
 * Both are read from the API one page at a time, newest first. The view on the
 * screen, its filters and its page are in the address, read and written by
 * audit-address.ts, so a reload or a shared link opens the same page. The
 * views are two links, each marked as the current page when it is, and moving
 * from one to the other moves focus to the heading of the new one.
 *
 * The trail is append only. Sending a failed confirmation again does not tidy
 * the failure away. The server writes a new email and an event saying it was
 * sent again, which is the whole point of keeping a trail.
 */

import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Mail, ScrollText } from 'lucide-react'
import { PageHeader } from '../../shared/ui'
import { AUDIT_LOG_PATH } from './admin-links'
import { readView, viewHref } from './audit-address'
import type { LogView } from './audit-address'
import AuditTrail from './AuditTrail'
import NotificationLog from './NotificationLog'

const VIEW_HEADING: Record<LogView, string> = {
  trail: 'Audit trail',
  notifications: 'Notification log',
}

const VIEW_HEADING_ID = 'log-view-heading'

function ViewLink({ view, current, children }: { view: LogView; current: LogView; children: ReactNode }) {
  const here = view === current
  return (
    <Link
      to={viewHref(AUDIT_LOG_PATH, view)}
      aria-current={here ? 'page' : undefined}
      className={here ? 'btn border-2 border-ink bg-surface px-md font-semibold text-ink' : 'btn-secondary px-md'}
    >
      {children}
    </Link>
  )
}

export default function AuditLog() {
  const [params] = useSearchParams()
  const view = readView(params)

  // The address is where the screen opens, and the router has already put
  // focus on the page. Only a change of view moves it, to the new heading.
  const heading = useRef<HTMLHeadingElement>(null)
  const viewBefore = useRef(view)
  useEffect(() => {
    if (viewBefore.current === view) return
    viewBefore.current = view
    heading.current?.focus()
  }, [view])

  return (
    <>
      <PageHeader
        screenId="SC-24"
        title="Audit and notification log"
        subtitle="Everything the system and the staff have done, and every email the system tried to send about it. Nothing here can be edited or removed."
      />
      <nav aria-label="Parts of the log" className="mb-lg">
        <ul className="flex flex-wrap gap-sm">
          <li>
            <ViewLink view="trail" current={view}>
              <ScrollText className="h-4 w-4 shrink-0" aria-hidden="true" />
              Audit trail
            </ViewLink>
          </li>
          <li>
            <ViewLink view="notifications" current={view}>
              <Mail className="h-4 w-4 shrink-0" aria-hidden="true" />
              Notification log
            </ViewLink>
          </li>
        </ul>
      </nav>
      <h2 id={VIEW_HEADING_ID} ref={heading} tabIndex={-1} className="mb-md text-lg font-semibold text-ink">
        {VIEW_HEADING[view]}
      </h2>
      {/* The key starts each view afresh, so nothing typed into one is left in the other. */}
      <div key={view}>{view === 'trail' ? <AuditTrail /> : <NotificationLog />}</div>
    </>
  )
}
