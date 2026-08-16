/**
 * SC-10 Counter Dashboard.
 *
 * The first screen counter staff see, and it has one job: answer "what do
 * I have to do today" without anybody having to read a table. The five
 * figures across the top are the whole answer, and each one opens the list
 * behind it rather than sending you off to find it.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, EmptyState, PageHeader, StatTile } from '../../shared/ui'
import { useSession } from '../../shared/session'
import { TODAY, auditEvents } from '../../shared/fixtures'
import { formatDate, formatDateTime, money } from '../../shared/format'
import type { BranchScope } from './counter-desk-data'
import * as desk from './counter-desk-data'
import type { FocusId } from './SC10-Focus-Panel'
import FocusPanel, { PanelLink } from './SC10-Focus-Panel'

const TILE_BUTTON =
  'block h-full w-full cursor-pointer rounded-lg text-left transition-shadow duration-200 [&>div]:h-full'

export default function CounterDashboard() {
  const { branch } = useSession()
  const [allBranches, setAllBranches] = useState(false)
  const [focus, setFocus] = useState<FocusId>('collections')
  const scope: BranchScope = allBranches ? 'ALL' : branch.code

  const today = useMemo(() => {
    const collections = desk.collectionsOn(TODAY, scope)
    const returns = desk.returnsOn(TODAY, scope)
    const week = desk.weekDays(TODAY)
    return {
      collections,
      waiting: collections.filter((c) => !c.rental && c.reservation.status !== 'NO_SHOW'),
      returns,
      stillOut: returns.filter((r) => r.outstandingUnits > 0),
      overdue: desk.overdueReturns(scope),
      quarantined: desk.assetsWithStatus('QUARANTINED', scope),
      reallocate: desk.bookingsNeedingReallocation(scope),
      onHire: desk.assetsWithStatus('ON_HIRE', scope),
      available: desk.assetsWithStatus('AVAILABLE', scope),
      weekCollections: week.reduce((n, d) => n + desk.collectionsOn(d, scope).length, 0),
    }
  }, [scope])

  const lateFees = today.overdue.reduce((sum, entry) => sum + desk.lateFeeRunning(entry), 0)

  const tiles = [
    {
      id: 'collections' as FocusId,
      label: 'Collections due today',
      value: today.collections.length,
      hint:
        today.waiting.length > 0
          ? `${today.waiting.length} still waiting at the counter`
          : 'All handed over',
      tone: today.waiting.length > 0 ? ('warn' as const) : ('good' as const),
    },
    {
      id: 'returns' as FocusId,
      label: 'Returns due today',
      value: today.returns.length,
      hint:
        today.stillOut.length > 0
          ? `${today.stillOut.length} still to come back`
          : 'Nothing outstanding for today',
      tone: today.stillOut.length > 0 ? ('warn' as const) : ('good' as const),
    },
    {
      id: 'overdue' as FocusId,
      label: 'Overdue now',
      value: today.overdue.length,
      hint: today.overdue.length > 0 ? `${money(lateFees)} in late fees running` : 'Nothing late',
      tone: today.overdue.length > 0 ? ('bad' as const) : ('good' as const),
    },
    {
      id: 'quarantine' as FocusId,
      label: 'Quarantined',
      value: today.quarantined.length,
      hint:
        today.quarantined.length > 0
          ? 'Withdrawn from hire until inspected'
          : 'Whole fleet is hireable',
      tone: today.quarantined.length > 0 ? ('bad' as const) : ('good' as const),
    },
    {
      id: 'reallocate' as FocusId,
      label: 'Bookings to reallocate',
      value: today.reallocate.length,
      hint:
        today.reallocate.length > 0
          ? 'A unit needs swapping before collection'
          : 'Every booking has a unit set aside',
      tone: today.reallocate.length > 0 ? ('warn' as const) : ('good' as const),
    },
  ]

  const activity = auditEvents.filter((event) => event.at.startsWith(TODAY))

  return (
    <div>
      <PageHeader
        screenId="SC-10"
        title="Today at the counter"
        subtitle={`${allBranches ? 'All three branches' : branch.name}, ${formatDate(TODAY)}. Tap a figure to see what sits behind it.`}
        actions={
          <Link to="/counter/booking" className="btn-primary">
            Start a booking
          </Link>
        }
      />

      <div
        role="group"
        aria-label="Which branches these figures cover"
        className="mb-lg flex flex-wrap gap-sm"
      >
        {[
          { on: false, label: branch.name },
          { on: true, label: 'All branches' },
        ].map((option) => (
          <button
            key={option.label}
            type="button"
            aria-pressed={allBranches === option.on}
            onClick={() => setAllBranches(option.on)}
            className={
              allBranches === option.on
                ? 'btn bg-accent font-semibold text-accent-ink'
                : 'btn-secondary'
            }
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="mb-lg grid gap-md sm:grid-cols-2 xl:grid-cols-5">
        {tiles.map((tile) => (
          <button
            key={tile.id}
            type="button"
            aria-pressed={focus === tile.id}
            onClick={() => setFocus(tile.id)}
            className={`${TILE_BUTTON} ${
              focus === tile.id ? 'ring-2 ring-accent ring-offset-2' : 'hover:shadow-raised'
            }`}
          >
            <StatTile label={tile.label} value={tile.value} hint={tile.hint} tone={tile.tone} />
          </button>
        ))}
      </div>

      <div className="mb-lg">
        <FocusPanel focus={focus} today={today} />
      </div>

      <div className="grid gap-md lg:grid-cols-3">
        <StatTile
          label="Out on hire now"
          value={today.onHire.length}
          hint="Units with a customer"
        />
        <StatTile
          label="Ready to hire"
          value={today.available.length}
          hint="On the shelf and serviceable"
          tone="good"
        />
        <StatTile
          label="Collections this week"
          value={today.weekCollections}
          hint="Monday to Sunday"
        />
      </div>

      <Card
        title="What has happened today"
        className="mt-lg"
        action={<PanelLink to="/counter/diary">Open the diary</PanelLink>}
      >
        {activity.length === 0 ? (
          <EmptyState
            title="Nothing logged yet today"
            body="Collections, returns and fee changes appear here as they happen."
          />
        ) : (
          <ul className="flex flex-col gap-md">
            {activity.map((event) => (
              <li key={event.id} className="flex flex-wrap items-baseline gap-sm">
                <span className="tabular font-mono text-xs text-slate-faint">
                  {formatDateTime(event.at)}
                </span>
                <span className="text-sm text-ink">{event.detail}</span>
                <span className="text-xs text-slate-soft">by {event.actor}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
