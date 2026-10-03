/**
 * SC-10 Counter Dashboard.
 *
 * The first screen counter staff see, and it answers one question: what do I
 * have to do today at this branch. Five figures across the top are the whole
 * answer, and the three lists under them say who is coming to collect, what is
 * due back and what is late, each with the way to deal with it one press away.
 *
 * It is one request for the branch the person works at, which comes from
 * work-branch.ts through the gate. Every count, every day late and every late
 * fee is the server's. The counts are true totals and each list holds at most
 * fifty, so a list that is cut short says so and points at the diary.
 *
 * The screen is left open all day. It reads the branch again whenever the
 * window comes back into focus, which is the cache's rule for the counter's
 * day, and the refresh button reads it again whenever someone asks. The line
 * above the figures says when they were read.
 */

import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { RotateCw } from 'lucide-react'
import type { CounterDashboard as Dashboard, DashboardCounts } from '../../shared/api/contract'
import { overviewQueries } from '../../shared/api/counter-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { formatDate } from '../../shared/format'
import { branchClockTime } from '../../shared/today'
import { EmptyState, PageHeader, StatTile } from '../../shared/ui'
import { DIARY_PATH, NEW_BOOKING_PATH } from './counter-links'
import { TodayLists } from './SC10-Today-Lists'
import { WorkBranchGate } from './work-branch-gate'
import type { CounterBranch } from './work-branch-gate'

/** One skeleton block for each figure. */
const FIGURE_COUNT = 5

type Tone = 'default' | 'warn' | 'bad' | 'good'

interface Figure {
  label: string
  value: number
  hint: string
  tone: Tone
}

/** The five figures, each with a sentence that says what it means, so the
 *  colour of a figure never carries the meaning alone. */
function figuresFor(counts: DashboardCounts): Figure[] {
  return [
    {
      label: 'Collections due today',
      value: counts.collectionsDue,
      hint: counts.collectionsDue > 0 ? 'Booked to go out today' : 'Nobody is booked to collect',
      tone: 'default',
    },
    {
      label: 'Returns due today',
      value: counts.returnsDue,
      hint: counts.returnsDue > 0 ? 'Due back before closing' : 'Nothing is due back',
      tone: 'default',
    },
    {
      label: 'Overdue now',
      value: counts.overdue,
      hint: counts.overdue > 0 ? 'Past the day they were due back' : 'Nothing is late',
      tone: counts.overdue > 0 ? 'bad' : 'good',
    },
    {
      label: 'Out on hire',
      value: counts.onHire,
      hint: 'With customers now',
      tone: 'default',
    },
    {
      label: 'Quarantined',
      value: counts.quarantined,
      hint: counts.quarantined > 0 ? 'Withdrawn from hire until inspected' : 'Nothing is withdrawn from hire',
      tone: counts.quarantined > 0 ? 'warn' : 'good',
    },
  ]
}

/** Whether there is nothing to collect, take back or chase today. */
function isQuietDay(counts: DashboardCounts): boolean {
  return counts.collectionsDue === 0 && counts.returnsDue === 0 && counts.overdue === 0
}

/** When the figures were read, as a time of day at the branch. */
function readAt(updatedAt: number): string {
  return branchClockTime(new Date(updatedAt).toISOString())
}

function QuietDay({ dashboard }: { dashboard: Dashboard }) {
  return (
    <div className="card">
      <EmptyState
        title={`Nothing is due at ${dashboard.branchName} today`}
        body="Nobody is booked to collect, nothing is due back and nothing is late. Bookings for other days are in the diary."
        action={
          <Link to={DIARY_PATH} className="btn-secondary px-md">
            Open the diary
          </Link>
        }
      />
    </div>
  )
}

function TodayAt({ branch }: { branch: CounterBranch }) {
  const dashboard = useQuery(overviewQueries.dashboard(branch.code))
  const phase = queryPhase(dashboard)
  const data = dashboard.data

  if (phase === 'failed') {
    return (
      <ErrorState
        what={`today's figures for ${branch.name}`}
        error={dashboard.error}
        onRetry={() => void dashboard.refetch()}
      />
    )
  }
  if (data === undefined) {
    return <LoadingState label={`Loading today at ${branch.name}`} shape="tiles" count={FIGURE_COUNT} />
  }

  const refreshing = dashboard.isFetching
  return (
    <div aria-busy={refreshing}>
      <div className="mb-lg flex flex-wrap items-center justify-between gap-sm">
        <p role="status" className="text-sm text-slate-soft">
          {data.branchName}, {formatDate(data.date)}.{' '}
          {refreshing ? 'Reading the figures again.' : `Read at ${readAt(dashboard.dataUpdatedAt)}.`}
        </p>
        <button
          type="button"
          className="btn-secondary px-md"
          onClick={() => void dashboard.refetch()}
          disabled={refreshing}
        >
          <RotateCw className="h-4 w-4 shrink-0" aria-hidden="true" />
          Refresh
        </button>
      </div>

      <div className="mb-lg grid gap-md sm:grid-cols-2 xl:grid-cols-5">
        {figuresFor(data.counts).map((figure) => (
          <StatTile key={figure.label} label={figure.label} value={figure.value} hint={figure.hint} tone={figure.tone} />
        ))}
      </div>

      {isQuietDay(data.counts) ? <QuietDay dashboard={data} /> : <TodayLists dashboard={data} />}
    </div>
  )
}

export default function CounterDashboard() {
  return (
    <>
      <PageHeader
        screenId="SC-10"
        title="Today at the counter"
        subtitle="What goes out, what comes back and what is late at your branch today."
        actions={
          <Link to={NEW_BOOKING_PATH} className="btn-primary">
            Start a booking
          </Link>
        }
      />
      <WorkBranchGate>{(branch) => <TodayAt branch={branch} />}</WorkBranchGate>
    </>
  )
}
