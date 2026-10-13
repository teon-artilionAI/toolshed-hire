/**
 * The closed days on the trading calendar, grouped by month.
 *
 * Each month is a heading and a list. A public holiday reads as closing every
 * branch and offers nothing, because the law fixes it. A closure day names its
 * branch, or every branch, and its reason, and offers to cancel it, which asks
 * first. Putting the question away gives focus back to the button that opened
 * it. Only one question is open at a time.
 */

import { useRef, useState } from 'react'
import type { CalendarClosedDay, ClosureDay } from '../../shared/api/contract'
import { KIND_LABEL, branchWords, dayWords, monthsOf } from './calendar-words'
import { CancelQuestion } from './SC19-Cancel-Question'

function ClosedDayEntry({
  closed,
  nameOf,
  asking,
  onAsk,
  onKeep,
  onCancelled,
}: {
  closed: CalendarClosedDay
  nameOf: (code: string) => string
  /** True while this closure's question is open. */
  asking: boolean
  onAsk: () => void
  onKeep: () => void
  onCancelled: (closure: ClosureDay) => void
}) {
  const buttonRef = useRef<HTMLButtonElement>(null)
  const branch = branchWords(closed.branchCode, nameOf)
  const when = dayWords(closed.day)
  const closureId = closed.closureId
  return (
    <li className="min-w-0 border-t border-line px-md py-sm first:border-t-0">
      <div className="flex flex-wrap items-start justify-between gap-sm">
        <div className="min-w-0">
          <p className="break-words text-sm font-semibold text-ink">{when}</p>
          <p className="break-words text-sm text-slate-soft">
            {KIND_LABEL[closed.kind]}, {closed.branchCode === null ? 'every branch' : branch}. {closed.reason}
          </p>
        </div>
        {closureId !== null && !asking && (
          <button
            ref={buttonRef}
            type="button"
            className="btn-secondary px-md"
            aria-label={`Cancel the closure of ${branch} on ${when}`}
            onClick={onAsk}
          >
            Cancel
          </button>
        )}
      </div>
      {closureId !== null && asking && (
        <CancelQuestion
          closure={closed}
          closureId={closureId}
          branchLabel={branch}
          onCancelled={onCancelled}
          onKeep={() => {
            onKeep()
            requestAnimationFrame(() => buttonRef.current?.focus())
          }}
        />
      )}
    </li>
  )
}

export function ClosedDays({
  days,
  nameOf,
  onCancelled,
}: {
  days: readonly CalendarClosedDay[]
  nameOf: (code: string) => string
  /** Called with the closure the server answered with, cancelled. */
  onCancelled: (closure: ClosureDay) => void
}) {
  const [asking, setAsking] = useState<string | null>(null)
  return (
    <div className="flex flex-col gap-lg">
      {monthsOf(days).map((month) => (
        <section key={month.key} aria-labelledby={`month-${month.key}`}>
          <h3 id={`month-${month.key}`} className="mb-sm text-base font-semibold text-ink">
            {month.label}
          </h3>
          <ul className="card">
            {month.days.map((closed) => (
              <ClosedDayEntry
                key={`${closed.day}-${closed.kind}-${closed.closureId ?? closed.reason}`}
                closed={closed}
                nameOf={nameOf}
                asking={closed.closureId !== null && asking === closed.closureId}
                onAsk={() => setAsking(closed.closureId)}
                onKeep={() => setAsking(null)}
                onCancelled={(closure) => {
                  setAsking(null)
                  onCancelled(closure)
                }}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
