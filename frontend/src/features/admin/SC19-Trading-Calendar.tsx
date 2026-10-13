/**
 * The trading calendar, a view of SC-19 at /admin/closure-days.
 *
 * The branches trade the week the server gives them and close on the public
 * holidays. Here the owner closes a branch, or every branch, on any other day,
 * a stocktake or a day the government declares, and opens one again. The view
 * is reached from the business overview and from the owner's menu.
 *
 * The closed days of the next twelve months are one request, grouped by month
 * with the shared loading, failed and empty states. Closing a day first lists
 * the bookings that start or end on it, because closing it cancels none of
 * them and the owner rings each customer. Once the server has answered a
 * close or a cancel, a notice above the form says what was done and takes
 * focus, and the calendar, the branch list every date picker steers by, and
 * the counter's day are read again.
 */

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { adminQueries } from '../../shared/api/admin-queries'
import type { CalendarQuery, ClosureDay } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { todayInBranchTime } from '../../shared/today'
import { EmptyState, Notice, PageHeader } from '../../shared/ui'
import { countOf } from '../counter/counter-labels'
import { ADMIN_HOME_PATH } from './admin-links'
import { branchWords, dayWords } from './calendar-words'
import { ClosedDays } from './SC19-Closed-Days'
import { ClosureForm } from './SC19-Closure-Form'
import { useBranchList } from './use-branch-list'

/** The span the server lists when none is asked for, today and the year after. */
const NEXT_TWELVE_MONTHS: CalendarQuery = {}
const SKELETON_ROWS = 3

interface Outcome {
  title: string
  line: string
}

export default function TradingCalendar() {
  const today = todayInBranchTime()
  const branches = useBranchList()
  const calendar = useQuery(adminQueries.calendar(NEXT_TWELVE_MONTHS))
  const phase = queryPhase(calendar)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const outcomeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (outcome !== null) outcomeRef.current?.focus()
  }, [outcome])

  function closed(closure: ClosureDay) {
    const where = branchWords(closure.branchCode, branches.nameOf)
    setOutcome({
      title: `${where} is closed on ${dayWords(closure.day)}`,
      line: 'Customers can no longer choose that day to collect or bring equipment back. Ring the customers whose bookings start or end that day.',
    })
  }

  function cancelled(closure: ClosureDay) {
    const where = branchWords(closure.branchCode, branches.nameOf)
    setOutcome({
      title: `${where} is open again on ${dayWords(closure.day)}`,
      line: 'Customers can choose that day again. The closure stays in the audit trail.',
    })
  }

  return (
    <>
      <PageHeader
        screenId="SC-19"
        title="Trading calendar"
        subtitle="The days a branch does not trade beyond its week and the public holidays, such as a stocktake or a day the government declares. Closing a day never cancels a booking."
        actions={
          <Link to={ADMIN_HOME_PATH} className="btn-secondary px-md">
            <ArrowLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
            Business overview
          </Link>
        }
      />
      {outcome !== null && (
        <div ref={outcomeRef} tabIndex={-1} className="mb-lg">
          <Notice tone="success" title={outcome.title}>
            <p>{outcome.line}</p>
          </Notice>
        </div>
      )}

      <section aria-labelledby="close-a-day-heading" className="mb-xl">
        <h2 id="close-a-day-heading" className="mb-md text-lg font-semibold text-ink">
          Close a day
        </h2>
        <ClosureForm today={today} branches={branches} onClosed={closed} />
      </section>

      <section aria-labelledby="closed-days-heading">
        <h2 id="closed-days-heading" className="mb-xs text-lg font-semibold text-ink">
          Closed days in the next twelve months
        </h2>
        <p role="status" className="mb-md text-sm text-slate-soft">
          {phase === 'ready' && calendar.data !== undefined
            ? `${countOf(calendar.data.items.length, 'closed day', 'closed days')}, public holidays included.`
            : phase === 'loading'
              ? 'Loading the closed days.'
              : ''}
        </p>
        {phase === 'failed' ? (
          <ErrorState what="the closed days" error={calendar.error} onRetry={() => void calendar.refetch()} />
        ) : calendar.data === undefined ? (
          <LoadingState shape="rows" count={SKELETON_ROWS} />
        ) : calendar.data.items.length === 0 ? (
          <div className="card">
            <EmptyState
              title="No day is closed in the next twelve months"
              body="Every branch trades its usual week. Close a day above when a branch will not trade."
            />
          </div>
        ) : (
          <div aria-busy={calendar.isFetching}>
            <ClosedDays days={calendar.data.items} nameOf={branches.nameOf} onCancelled={cancelled} />
          </div>
        )}
      </section>
    </>
  )
}
