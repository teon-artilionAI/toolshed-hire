/**
 * The figures on SC-19 above the branches.
 *
 * What is due and where the fleet stands across the business today, how the
 * month is going, and the three things that wait on the owner. Each of the
 * last two groups is a set of links, because a figure the owner has to act on
 * should be one press from the screen where they act. Every figure is the
 * server's, and each says in words what it means, so a colour never carries
 * the meaning alone.
 */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import type { AdminDashboard, FleetCounts, MonthToDate } from '../../shared/api/contract'
import { isNegativeMoney, money } from '../../shared/format'
import { StatTile } from '../../shared/ui'
import {
  ASSET_REGISTER_PATH,
  CUSTOMER_HOLDS_PATH,
  NOTIFICATION_LOG_PATH,
  reportHref,
} from './admin-links'
import { DEFAULT_GROUPING } from './report-address'
import { GROSS_CONTRIBUTION, periodWords, utilisationWords } from './report-labels'

const SECTION_HEADING = 'mb-md text-sm font-semibold uppercase tracking-wide text-slate-soft'

/** A figure the owner can press, which opens the screen where it is dealt with. */
function FigureLink({
  to,
  label,
  value,
  hint,
  action,
}: {
  to: string
  label: string
  value: string | number
  hint: string
  /** Says where the link goes, for example "Open the asset register". */
  action: string
}) {
  return (
    // The spaces between the parts keep the name of the link a sentence a
    // screen reader can read, whatever the parts are drawn as.
    <Link to={to} className="card block p-lg transition-colors hover:bg-muted">
      <span className="block text-xs font-semibold uppercase tracking-wide text-slate-soft">{label}</span>{' '}
      <span className="tabular mt-sm block text-3xl font-semibold text-ink">{value}</span>{' '}
      <span className="mt-xs block text-sm text-slate-soft">{hint}</span>{' '}
      <span className="mt-sm flex items-center gap-xs text-sm font-medium text-ink">
        {action}
        <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
      </span>
    </Link>
  )
}

function FigureSection({ id, heading, children }: { id: string; heading: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="mb-lg">
      <h2 id={id} className={SECTION_HEADING}>
        {heading}
      </h2>
      {children}
    </section>
  )
}

/** The business today, the server's totals across every branch. */
export function FleetToday({ totals }: { totals: FleetCounts }) {
  return (
    <FigureSection id="fleet-today-heading" heading="Across the business today">
      <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Collections due today" value={totals.collectionsDue} hint="Booked to go out today" />
        <StatTile label="Returns due today" value={totals.returnsDue} hint="Due back before closing" />
        <StatTile
          label="Overdue now"
          value={totals.overdue}
          tone={totals.overdue > 0 ? 'bad' : 'good'}
          hint={totals.overdue > 0 ? 'Past the day they were due back' : 'Nothing is late'}
        />
        <StatTile label="Out on hire" value={totals.onHire} hint="With customers now" />
        <StatTile label="On the shelf" value={totals.available} hint="Ready to hire" />
        <StatTile
          label="Quarantined"
          value={totals.quarantined}
          tone={totals.quarantined > 0 ? 'warn' : 'good'}
          hint={totals.quarantined > 0 ? 'Withdrawn from hire until inspected' : 'Nothing is withdrawn from hire'}
        />
        <StatTile
          label="In the workshop"
          value={totals.underRepair}
          tone={totals.underRepair > 0 ? 'warn' : 'good'}
          hint={totals.underRepair > 0 ? 'Being repaired, not hireable' : 'Nothing is being repaired'}
        />
      </div>
    </FigureSection>
  )
}

/** The month so far, each figure opening the report for the same period. */
export function MonthSoFar({ month }: { month: MonthToDate }) {
  const report = reportHref(month, DEFAULT_GROUPING)
  const period = periodWords(month.from, month.to)
  return (
    <FigureSection id="month-heading" heading="This month so far">
      <div className="grid gap-md sm:grid-cols-2">
        <FigureLink
          to={report}
          label="Utilisation this month"
          value={utilisationWords(month.utilisationPercent)}
          hint={period}
          action="Open the report for this month"
        />
        <FigureLink
          to={report}
          label={`${GROSS_CONTRIBUTION} this month`}
          value={money(month.grossContribution)}
          hint={
            isNegativeMoney(month.grossContribution)
              ? 'Below zero. Repairs cost more than the fleet brought in. Not profit.'
              : 'Revenue and recoveries less repair costs, excluding VAT. Not profit.'
          }
          action="Open the report for this month"
        />
      </div>
    </FigureSection>
  )
}

/** What waits on the owner, each opening the screen where it is dealt with. */
export function NeedsAttention({ dashboard }: { dashboard: AdminDashboard }) {
  const { openDamageReports, customersOnHold, failedNotifications } = dashboard
  return (
    <FigureSection id="attention-heading" heading="Waiting on you">
      <div className="grid gap-md sm:grid-cols-3">
        <FigureLink
          to={ASSET_REGISTER_PATH}
          label="Open damage reports"
          value={openDamageReports}
          hint={openDamageReports > 0 ? 'Units waiting on a repair or a write off' : 'No damage report is open'}
          action="Open the asset register"
        />
        <FigureLink
          to={CUSTOMER_HOLDS_PATH}
          label="Customers on hold"
          value={customersOnHold}
          hint={customersOnHold > 0 ? 'Cannot book until the hold is lifted' : 'Nobody is on hold'}
          action="Open the customer holds"
        />
        <FigureLink
          to={NOTIFICATION_LOG_PATH}
          label="Failed notifications"
          value={failedNotifications}
          hint={failedNotifications > 0 ? 'Emails that did not reach the customer' : 'Every email went out'}
          action="Open the notification log"
        />
      </div>
    </FigureSection>
  )
}
