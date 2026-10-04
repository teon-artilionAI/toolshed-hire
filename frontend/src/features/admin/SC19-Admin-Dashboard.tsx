/**
 * SC-19 Admin Dashboard.
 *
 * The owner's screen. It answers one question first, "where does the business
 * stand this morning", across all three branches, and then says how the month
 * is going, what is waiting on the owner, and where each branch stands.
 *
 * It is one request, `GET /api/admin/dashboard`, and every figure on it is the
 * server's. The totals are the server's totals and not a sum of the branches,
 * and the month's utilisation and gross contribution are the server's too.
 * The figures link to where the owner would go next. The month opens the
 * report for the same period, the damage reports open the asset register, the
 * holds open the customer holds, the failed notifications open the log, and
 * what is due at a branch opens that branch's diary.
 *
 * The screen is left open all day. It reads the figures again whenever the
 * window comes back into focus, which is the cache's rule for the dashboard,
 * and the refresh button reads them again whenever the owner asks. The line
 * above the figures says when they were read.
 */

import { useQuery } from '@tanstack/react-query'
import { RotateCw } from 'lucide-react'
import type { AdminDashboard as Dashboard } from '../../shared/api/contract'
import { adminQueries } from '../../shared/api/admin-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { formatDate } from '../../shared/format'
import { branchClockTime } from '../../shared/today'
import { PageHeader } from '../../shared/ui'
import { BranchCards } from './SC19-Branch-Cards'
import { FleetToday, MonthSoFar, NeedsAttention } from './SC19-Figures'

/** One skeleton block for each figure of the business today. */
const FIGURE_COUNT = 7

/** When the figures were read, as a time of day at the branches. */
function readAt(updatedAt: number): string {
  return branchClockTime(new Date(updatedAt).toISOString())
}

function Overview({
  dashboard,
  refreshing,
  readAtTime,
  onRefresh,
}: {
  dashboard: Dashboard
  refreshing: boolean
  readAtTime: string
  onRefresh: () => void
}) {
  return (
    <div aria-busy={refreshing}>
      <div className="mb-lg flex flex-wrap items-center justify-between gap-sm">
        <p role="status" className="text-sm text-slate-soft">
          Every branch, {formatDate(dashboard.date)}.{' '}
          {refreshing ? 'Reading the figures again.' : `Read at ${readAtTime}.`}
        </p>
        <button type="button" className="btn-secondary px-md" onClick={onRefresh} disabled={refreshing}>
          <RotateCw className="h-4 w-4 shrink-0" aria-hidden="true" />
          Refresh
        </button>
      </div>
      <FleetToday totals={dashboard.totals} />
      <MonthSoFar month={dashboard.monthToDate} />
      <NeedsAttention dashboard={dashboard} />
      <BranchCards branches={dashboard.branches} />
    </div>
  )
}

export default function AdminDashboard() {
  const dashboard = useQuery(adminQueries.dashboard())
  const phase = queryPhase(dashboard)
  const data = dashboard.data

  return (
    <>
      <PageHeader
        screenId="SC-19"
        title="Business overview"
        subtitle="Where the three branches stand today, how the month is going, and what is waiting on you."
      />
      {phase === 'failed' ? (
        <ErrorState
          what="the business overview"
          error={dashboard.error}
          onRetry={() => void dashboard.refetch()}
        />
      ) : data === undefined ? (
        <LoadingState label="Loading the business overview" shape="tiles" count={FIGURE_COUNT} />
      ) : (
        <Overview
          dashboard={data}
          refreshing={dashboard.isFetching}
          readAtTime={readAt(dashboard.dataUpdatedAt)}
          onRefresh={() => void dashboard.refetch()}
        />
      )}
    </>
  )
}
