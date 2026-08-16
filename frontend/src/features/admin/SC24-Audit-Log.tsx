/**
 * SC-24, Audit and notification log.
 *
 * Two records that only make sense side by side. The audit trail says what
 * the business did, and the delivery log says whether the customer ever
 * heard about it. When somebody arrives insisting they were never told, the
 * answer is on this screen.
 *
 * The trail is append only. Re-sending a failed confirmation does not tidy
 * the failure away; it writes a second line saying it was sent again, which
 * is the whole point of keeping a trail.
 */

import { useEffect, useMemo, useState } from 'react'
import { TODAY, auditEvents, notifications } from '../../shared/fixtures'
import type { AuditEvent, NotificationRecord } from '../../shared/types'
import {
  Card,
  Notice,
  PageHeader,
  StatTile,
} from '../../shared/ui'
import { useSession } from '../../shared/session'
import AuditTrail from './AuditTrail'
import NotificationLog from './NotificationLog'

/** Long enough to read as a real attempt on a real mail server. */
const SEND_MS = 800

/**
 * The prototype runs on a fixed "today" so that overdue hires and due dates
 * stay meaningful. A new entry therefore takes the fixture date with the
 * real clock time, rather than a real date months away from everything else
 * on screen.
 */
function stampNow(): string {
  return `${TODAY}T${new Date().toTimeString().slice(0, 8)}`
}

export default function AuditLog() {
  const { user } = useSession()
  const [events, setEvents] = useState<AuditEvent[]>(auditEvents)
  const [records, setRecords] = useState<NotificationRecord[]>(notifications)
  const [sending, setSending] = useState<NotificationRecord | null>(null)
  const [sent, setSent] = useState<string | null>(null)

  const failedCount = records.filter((r) => !r.delivered).length
  const actorCount = useMemo(
    () => new Set(events.map((e) => e.actor)).size,
    [events],
  )

  useEffect(() => {
    if (!sending) return
    const timer = window.setTimeout(() => {
      setRecords((current) =>
        current.map((r) => (r.id === sending.id ? { ...r, delivered: true } : r)),
      )
      setEvents((trail) => [
        {
          id: `ae-resend-${sending.id}-${trail.length}`,
          at: stampNow(),
          actor: user?.name ?? 'Admin',
          action: 'NOTIFICATION_RESENT',
          entity: sending.reference,
          detail: `Booking confirmation sent again to ${sending.to}`,
        },
        ...trail,
      ])
      setSent(sending.to)
      setSending(null)
    }, SEND_MS)
    return () => window.clearTimeout(timer)
  }, [sending, user])

  function handleResend(record: NotificationRecord) {
    setSent(null)
    setSending(record)
  }

  return (
    <>
      <PageHeader
        screenId="SC-24"
        title="Audit and notification log"
        subtitle="Everything the system and the staff have done, and every email we tried to send about it. Nothing here can be edited or removed."
      />

      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Entries recorded"
          value={events.length}
          hint="Append only, oldest kept forever"
        />
        <StatTile
          label="People and systems acting"
          value={actorCount}
          hint="Staff, customers and the overnight job"
        />
        <StatTile
          label="Emails attempted"
          value={records.length}
          hint="Booking confirmations sent to customers"
        />
        <StatTile
          label="Emails that did not arrive"
          value={failedCount}
          tone={failedCount > 0 ? 'bad' : 'good'}
          hint={
            failedCount > 0
              ? 'Somebody is waiting on a confirmation'
              : 'Every confirmation reached its mailbox'
          }
        />
      </div>

      {failedCount > 0 && (
        <div className="mb-lg">
          <Notice
            tone="error"
            title={`${failedCount} booking ${
              failedCount === 1 ? 'confirmation' : 'confirmations'
            } never reached the customer`}
          >
            Check the address is right, then try sending it again from the
            delivery log below. If it fails a second time, phone the customer
            and read the reference to them.
          </Notice>
        </div>
      )}

      {sent && (
        <div className="mb-lg">
          <Notice tone="success" title="Confirmation sent">
            The booking confirmation went out to {sent}. A line has been added
            to the audit trail recording who sent it and when.
          </Notice>
        </div>
      )}

      <div className="mb-lg">
        <Card title="Email delivery log">
          <NotificationLog
            records={records}
            sendingId={sending?.id ?? null}
            onResend={handleResend}
          />
        </Card>
      </div>

      <Card title="Audit trail">
        <div className="mb-lg">
          <Notice tone="info" title="This record cannot be changed">
            Entries are written as things happen and are never edited or
            deleted, including by an admin. Correcting something adds a new
            entry rather than rewriting an old one.
          </Notice>
        </div>
        <AuditTrail events={events} />
      </Card>
    </>
  )
}
