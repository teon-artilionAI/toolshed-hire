/**
 * One email in the notification log on SC-24.
 *
 * Each email says what it was about, who it went to, where it stands in words
 * beside its colour, when it was queued and sent, and how many attempts it
 * took. One that sends a failed email again says so. A failed one shows what
 * the mail provider said and offers "Send again".
 *
 * "Send again" asks first, in words that say a new email goes out and the
 * failed one stays in the log as it is. Only then does one button post the
 * re-send. The answer is the new email, and the log is read again so the new
 * attempt is on it.
 */

import { useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import type { EmailNotification, NotificationType } from '../../shared/api/contract'
import { ErrorState } from '../../shared/async-states'
import { branchDateTime } from '../../shared/today'
import { Notice, StatusPill } from '../../shared/ui'
import { NOTIFICATION_STATUS_LABEL, NOTIFICATION_STATUS_PILL } from './audit-words'
import { useResend } from './use-resend'

/** What each kind of email is, in words. */
const NOTIFICATION_TYPE_LABEL: Record<NotificationType, string> = {
  BOOKING_CONFIRMATION: 'Booking confirmation',
}

/** Said when a failed email carries no message from the provider. */
const NO_ERROR_GIVEN = 'The mail provider gave no reason.'

function Detail({ term, children }: { term: string; children: string }) {
  return (
    <div className="flex flex-wrap gap-x-sm">
      <dt className="text-slate-soft">{term}</dt>
      <dd className="min-w-0 break-words text-ink">{children}</dd>
    </div>
  )
}

/** The failed email's way to be sent again, with its question and its answer. */
function SendAgain({ notification }: { notification: EmailNotification }) {
  const resend = useResend(notification.id)
  const [asking, setAsking] = useState(false)
  const questionRef = useRef<HTMLHeadingElement>(null)
  const answerRef = useRef<HTMLDivElement>(null)
  const askRef = useRef<HTMLButtonElement>(null)
  const askedBefore = useRef(asking)
  const what = `${NOTIFICATION_TYPE_LABEL[notification.type].toLowerCase()} for ${notification.reservationReference}`

  // Opening the question puts focus on it, and closing it puts focus back on
  // the button that opened it. The answer takes focus when it arrives.
  useEffect(() => {
    if (askedBefore.current === asking) return
    askedBefore.current = asking
    if (asking) questionRef.current?.focus()
    else askRef.current?.focus()
  }, [asking])
  useEffect(() => {
    if (resend.sent !== null) answerRef.current?.focus()
  }, [resend.sent])

  if (resend.sent !== null) {
    return (
      <div ref={answerRef} tabIndex={-1} className="mt-md">
        <Notice tone="success" title={`The ${what} is sent again`}>
          <p>
            The new attempt to {resend.sent.recipientEmail} is{' '}
            {NOTIFICATION_STATUS_LABEL[resend.sent.status].toLowerCase()}. It is a new line in the log, and this one
            stays as it was.
          </p>
        </Notice>
      </div>
    )
  }

  if (!asking) {
    return (
      <button ref={askRef} type="button" className="btn-primary mt-md px-md" onClick={() => setAsking(true)}>
        <Send className="h-4 w-4 shrink-0" aria-hidden="true" />
        Send again <span className="sr-only">the {what}</span>
      </button>
    )
  }

  const failure = resend.failure
  const headingId = `resend-${notification.id}`
  return (
    <section aria-labelledby={headingId} className="mt-md rounded-lg border-2 border-ink p-md">
      <h4 id={headingId} ref={questionRef} tabIndex={-1} className="text-base font-semibold text-ink">
        Send the {what} again?
      </h4>
      <p className="mt-xs break-words text-sm text-ink">
        A new email goes to {notification.recipientEmail}. This failed attempt stays in the log as it is, so the
        failure and the second attempt can both be read later.
      </p>
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-sm">
          <ErrorState heading="We could not send it again" error={failure.error} onRetry={resend.send} />
        </div>
      )}
      {failure !== null && failure.kind !== 'fault' && (
        <div className="mt-sm">
          <Notice tone="error" title="The email was not sent again">
            <p>{failure.detail}</p>
          </Notice>
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button type="button" className="btn-primary px-md" disabled={resend.pending} onClick={resend.send}>
          <Send className="h-4 w-4 shrink-0" aria-hidden="true" />
          {resend.pending ? 'Sending it again' : 'Yes, send it again'}
        </button>
        <button
          type="button"
          className="btn-secondary px-md"
          disabled={resend.pending}
          onClick={() => {
            resend.clearFailure()
            setAsking(false)
          }}
        >
          Keep it as it is
        </button>
      </div>
      <p role="status" className="sr-only">
        {resend.pending ? 'Sending the email again, please wait.' : ''}
      </p>
    </section>
  )
}

export function NotificationEntry({
  notification,
  original,
}: {
  notification: EmailNotification
  /** The failed email this one sends again, when it is on the same page. */
  original: EmailNotification | undefined
}) {
  const titleId = `notification-${notification.id}`
  const failed = notification.status === 'FAILED'
  return (
    <article aria-labelledby={titleId} className="card min-w-0 p-md">
      <div className="flex flex-wrap items-start justify-between gap-sm">
        <h3 id={titleId} className="min-w-0 break-words text-base font-semibold text-ink">
          {NOTIFICATION_TYPE_LABEL[notification.type]} for {notification.reservationReference}
        </h3>
        <StatusPill
          status={NOTIFICATION_STATUS_PILL[notification.status]}
          label={NOTIFICATION_STATUS_LABEL[notification.status]}
        />
      </div>
      <dl className="tabular mt-sm grid gap-xs text-sm">
        <Detail term="Sent to">{notification.recipientEmail}</Detail>
        <Detail term="Subject">{notification.subject}</Detail>
        <Detail term="Queued">{branchDateTime(notification.queuedAt)}</Detail>
        <Detail term="Went out">
          {notification.sentAt !== null ? branchDateTime(notification.sentAt) : failed ? 'No' : 'Not yet'}
        </Detail>
        <Detail term="Attempts">{String(notification.attempts)}</Detail>
      </dl>
      {notification.resendOf !== null && (
        <p className="mt-sm text-sm text-slate-soft">
          {original === undefined
            ? 'This sends again an email that did not go out.'
            : `This sends again the email queued ${branchDateTime(original.queuedAt)}, which did not go out.`}
        </p>
      )}
      {failed && (
        <div className="mt-sm rounded border-l-4 border-status-overdue bg-status-overdue-wash p-sm text-sm">
          <p className="font-semibold text-status-overdue">What went wrong</p>
          <p className="mt-xs break-words text-ink">{notification.lastError ?? NO_ERROR_GIVEN}</p>
        </div>
      )}
      {failed && <SendAgain notification={notification} />}
    </article>
  )
}
