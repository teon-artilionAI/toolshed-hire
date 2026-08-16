/**
 * SC-19 Admin Dashboard.
 *
 * The owner's screen. It answers one question first, "where does the
 * business stand this morning", and then lets that answer be taken apart
 * branch by branch. The sums live in admin-fleet.ts and the chart in
 * SC19-Utilisation-Chart.tsx, so this file stays about what the owner sees
 * and what happens when they touch it.
 */

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, RefreshCw } from 'lucide-react'
import type { BranchCode } from '../../shared/types'
import {
  assets, auditEvents, branches, damageReports, productModels, TODAY,
} from '../../shared/fixtures'
import {
  Card, DataTable, EmptyState, Notice, PageHeader, StatTile, StatusPill,
} from '../../shared/ui'
import { daysOverdue, formatDate, formatDateTime, money } from '../../shared/format'
import { BRANCH_POSITIONS, UTILISATION_TARGET, combine, overdueRentalsAt } from './admin-fleet'
import UtilisationChart from './SC19-Utilisation-Chart'

type Scope = BranchCode | 'ALL'

const LOAD_MS = 450

const SEVERITY_LABEL = { MINOR: 'Minor', MODERATE: 'Moderate', SEVERE: 'Severe' }

function TileSkeleton() {
  return (
    <div className="card animate-pulse p-lg" aria-hidden="true">
      <div className="h-3 w-24 rounded bg-muted" />
      <div className="mt-sm h-8 w-20 rounded bg-muted" />
      <div className="mt-sm h-3 w-32 rounded bg-muted" />
    </div>
  )
}

export default function AdminDashboard() {
  const [scope, setScope] = useState<Scope>('ALL')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!loading) return
    const timer = window.setTimeout(() => setLoading(false), LOAD_MS)
    return () => window.clearTimeout(timer)
  }, [loading])

  const rows = useMemo(
    () => (scope === 'ALL' ? BRANCH_POSITIONS : BRANCH_POSITIONS.filter((p) => p.code === scope)),
    [scope],
  )
  const scopeName =
    scope === 'ALL' ? 'all three branches' : rows[0]?.name ?? 'this branch'
  const total = useMemo(() => combine(rows, scopeName), [rows, scopeName])

  const lateRentals = rows.flatMap((r) => overdueRentalsAt(r.code))
  const openDamage = damageReports.filter((d) => {
    if (d.status === 'RESOLVED') return false
    const asset = assets.find((a) => a.id === d.assetId)
    return scope === 'ALL' || asset?.branchCode === scope
  })
  const unpublished = scope === 'ALL' ? productModels.filter((m) => !m.published) : []
  const attentionCount = lateRentals.length + openDamage.length + unpublished.length

  return (
    <>
      <PageHeader
        screenId="SC-19"
        title="Business overview"
        subtitle={`Where the three branches stand as at ${formatDate(TODAY)}. Choose a branch to look at it on its own.`}
        actions={
          <>
            <button type="button" className="btn-secondary px-md" onClick={() => setLoading(true)}>
              <RefreshCw className="h-4 w-4 shrink-0" aria-hidden="true" />
              Refresh figures
            </button>
            <Link to="/admin/reports" className="btn-primary px-md">Open the full report</Link>
          </>
        }
      />

      <div
        className="mb-lg flex flex-wrap gap-sm"
        role="group"
        aria-label="Show all branches or one branch"
      >
        {(['ALL', ...branches.map((b) => b.code)] as Scope[]).map((code) => {
          const label =
            code === 'ALL' ? 'All branches' : branches.find((b) => b.code === code)?.name ?? code
          const selected = scope === code
          return (
            <button
              key={code}
              type="button"
              aria-pressed={selected}
              onClick={() => setScope(code)}
              className={
                selected
                  ? 'btn bg-accent px-md font-semibold text-accent-ink'
                  : 'btn-secondary px-md'
              }
            >
              {label}
            </button>
          )
        })}
      </div>

      {loading ? (
        <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4" aria-busy="true">
          <p role="status" className="sr-only">Working out the latest figures</p>
          {[0, 1, 2, 3].map((i) => <TileSkeleton key={i} />)}
        </div>
      ) : (
        <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Fleet on hire"
            value={`${total.utilisation}%`}
            hint={`${total.onHire} of ${total.units} units out, target ${UTILISATION_TARGET}%`}
            tone={total.utilisation >= UTILISATION_TARGET ? 'good' : 'warn'}
          />
          <StatTile
            label="Hire value on the books"
            value={money(total.booked)}
            hint={`${money(total.chargedToDate)} charged so far`}
          />
          <StatTile
            label="Overdue exposure"
            value={money(total.exposure)}
            hint={`${total.unitsOverdue} unit${total.unitsOverdue === 1 ? '' : 's'} still out past the due date`}
            tone={total.exposure > 0 ? 'bad' : 'good'}
          />
          <StatTile
            label="Units off the road"
            value={total.offRoad}
            hint="Quarantined or in for repair, earning nothing"
            tone={total.offRoad > 0 ? 'warn' : 'good'}
          />
        </div>
      )}

      {!loading && total.unitsOverdue > 0 && (
        <div className="mb-lg">
          <Notice tone="warn" title="Kit is out past its due date">
            {total.unitsOverdue} unit{total.unitsOverdue === 1 ? ' is' : 's are'} still with
            customers after the return date, worth {money(total.exposure)} in replacement value
            and unpaid late fees. Chase these before signing off the day.
          </Notice>
        </div>
      )}

      <div className="mb-lg grid gap-md lg:grid-cols-2">
        <Card title="Fleet utilisation by branch">
          <UtilisationChart rows={rows} />
        </Card>

        <Card title={`Needs attention (${attentionCount})`}>
          {attentionCount === 0 ? (
            <EmptyState
              title="Nothing needs attention here"
              body={`Every unit at ${scopeName} is accounted for, nothing is overdue and no damage report is open.`}
            />
          ) : (
            <ul className="flex flex-col gap-md">
              {lateRentals.map((rental) => (
                <li key={rental.id} className="flex flex-wrap items-center justify-between gap-sm">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink">
                      <span className="font-mono">{rental.reference}</span> is{' '}
                      {daysOverdue(rental.dueBackOn)} days late
                    </p>
                    <p className="text-xs text-slate-soft">
                      Was due back {formatDate(rental.dueBackOn)} at {rental.branchCode}
                    </p>
                  </div>
                  <StatusPill status={rental.status} />
                </li>
              ))}
              {openDamage.map((report) => {
                const asset = assets.find((a) => a.id === report.assetId)
                return (
                  <li key={report.id} className="flex flex-wrap items-center justify-between gap-sm">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-ink">
                        <span className="font-mono">{asset?.tag}</span> has a damage report open
                      </p>
                      <p className="text-xs text-slate-soft">
                        {SEVERITY_LABEL[report.severity]} damage, repair estimated at{' '}
                        {money(report.estimatedRepairCost)}
                      </p>
                    </div>
                    <Link to="/admin/assets" className="btn-secondary px-md text-sm">
                      Resolve it
                      <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                    </Link>
                  </li>
                )
              })}
              {unpublished.map((model) => (
                <li key={model.id} className="flex flex-wrap items-center justify-between gap-sm">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink">{model.name} is not published</p>
                    <p className="text-xs text-slate-soft">
                      Customers cannot see it or book it in the catalogue
                    </p>
                  </div>
                  <Link to="/admin/catalogue" className="btn-secondary px-md text-sm">
                    Open the catalogue
                    <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="mb-lg">
        <Card title="Branch by branch">
          <DataTable
            caption="Fleet position and hire value at each branch. Choose a branch name to look at it on its own."
            columns={[
              'Branch', 'Units', 'On hire', 'Available', 'Off the road',
              'On hire %', 'Hire value booked', 'Overdue exposure',
            ]}
          >
            {BRANCH_POSITIONS.map((position) => (
              <tr key={position.code} className={scope === position.code ? 'bg-accent-wash' : undefined}>
                <td className="td">
                  <button
                    type="button"
                    aria-current={scope === position.code ? 'true' : undefined}
                    onClick={() => setScope(position.code)}
                    className="btn -my-xs justify-start px-sm text-left font-semibold text-ink hover:bg-muted"
                  >
                    {position.name}
                    <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                  </button>
                </td>
                <td className="td tabular">{position.units}</td>
                <td className="td tabular">{position.onHire}</td>
                <td className="td tabular">{position.available}</td>
                <td className="td tabular">{position.offRoad}</td>
                <td className="td tabular font-semibold">{position.utilisation}%</td>
                <td className="td tabular">{money(position.booked)}</td>
                <td className="td tabular">{money(position.exposure)}</td>
              </tr>
            ))}
          </DataTable>
        </Card>
      </div>

      <Card
        title="Latest activity"
        action={
          <Link to="/admin/audit" className="btn-ghost px-sm text-sm">
            See the full log
            <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
          </Link>
        }
      >
        <ul className="flex flex-col gap-md">
          {auditEvents.slice(0, 5).map((event) => (
            <li key={event.id} className="border-l-2 border-line pl-md">
              <p className="text-sm text-ink">{event.detail}</p>
              <p className="mt-xs text-xs text-slate-soft">
                {formatDateTime(event.at)} by {event.actor === 'system' ? 'the system' : event.actor}
              </p>
            </li>
          ))}
        </ul>
      </Card>
    </>
  )
}
