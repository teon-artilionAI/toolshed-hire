/**
 * One card for each branch on SC-19.
 *
 * Each card says what is due at the branch today and where its fleet stands,
 * as the server counts it. What is due today is a link to the branch diary.
 * The diary works at the branch chosen for the tab, which an administrator
 * picks through the counter's branch helper, so following the link chooses
 * that branch first and the diary opens on it without asking.
 */

import { Link } from 'react-router-dom'
import { ArrowRight, MapPin } from 'lucide-react'
import type { DashboardBranch } from '../../shared/api/contract'
import { EmptyState } from '../../shared/ui'
import { DIARY_PATH } from '../counter/counter-links'
import { countOf } from '../counter/counter-labels'
import { chooseWorkBranch } from '../counter/work-branch'

/** What is due at a branch today, as the server counts it, in one line. */
function dueTodayWords(branch: DashboardBranch): string {
  const collections = countOf(branch.collectionsDue, 'collection', 'collections')
  const returns = countOf(branch.returnsDue, 'return', 'returns')
  return `${collections}, ${returns}, ${branch.overdue} overdue`
}

function DueToday({ branch }: { branch: DashboardBranch }) {
  return (
    <Link
      to={DIARY_PATH}
      onClick={() => chooseWorkBranch(branch.branchCode)}
      className="block rounded border border-line px-md py-sm transition-colors hover:bg-muted"
    >
      <span className="block text-xs font-semibold uppercase tracking-wide text-slate-soft">Due today</span>{' '}
      <span className="mt-xs block text-sm text-ink">{dueTodayWords(branch)}</span>{' '}
      <span className="mt-xs flex items-center gap-xs text-sm font-medium text-ink">
        Open the diary at {branch.branchName}
        <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
      </span>
    </Link>
  )
}

function FleetLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline justify-between gap-md">
      <dt className="text-sm text-slate-soft">{label}</dt>
      <dd className="tabular text-sm font-semibold text-ink">{value}</dd>
    </div>
  )
}

function BranchCard({ branch }: { branch: DashboardBranch }) {
  const headingId = `branch-${branch.branchCode}-heading`
  return (
    <article aria-labelledby={headingId} className="card flex flex-col gap-md p-lg">
      <h3 id={headingId} className="flex items-center gap-sm text-base font-semibold text-ink">
        <MapPin className="h-5 w-5 shrink-0 text-slate-faint" aria-hidden="true" />
        {branch.branchName}
      </h3>
      <DueToday branch={branch} />
      <dl className="flex flex-col gap-xs">
        <FleetLine label="Out on hire" value={branch.onHire} />
        <FleetLine label="On the shelf" value={branch.available} />
        <FleetLine label="Quarantined" value={branch.quarantined} />
        <FleetLine label="In the workshop" value={branch.underRepair} />
      </dl>
    </article>
  )
}

export function BranchCards({ branches }: { branches: readonly DashboardBranch[] }) {
  return (
    <section aria-labelledby="branches-heading">
      <h2 id="branches-heading" className="mb-md text-sm font-semibold uppercase tracking-wide text-slate-soft">
        Branch by branch
      </h2>
      {branches.length === 0 ? (
        <div className="card">
          <EmptyState
            title="No branch is listed"
            body="The server sent no branch with today's figures. The totals above still stand."
          />
        </div>
      ) : (
        <div className="grid gap-md md:grid-cols-3">
          {branches.map((branch) => (
            <BranchCard key={branch.branchCode} branch={branch} />
          ))}
        </div>
      )}
    </section>
  )
}
