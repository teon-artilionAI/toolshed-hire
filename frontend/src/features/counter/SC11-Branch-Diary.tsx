/**
 * SC-11 Branch Diary.
 *
 * This screen replaces the paper book the branches run on today, so it has
 * to do everything the book does and then the things the book cannot: show
 * a whole week at once, carry yesterday's uncollected hire forward instead
 * of leaving it on a page nobody turns back to, and record a no-show at the
 * moment it happens rather than in a margin.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarCheck, ChevronLeft, ChevronRight } from 'lucide-react'
import {
  Card,
  DataTable,
  EmptyState,
  Field,
  Notice,
  PageHeader,
  StatusPill,
} from '../../shared/ui'
import { useSession } from '../../shared/session'
import { TODAY, branches } from '../../shared/fixtures'
import { formatDate, formatDateTime } from '../../shared/format'
import type { BranchCode } from '../../shared/types'
import * as desk from './counter-desk-data'
import DiaryWeek from './SC11-Week-Grid'
import NoShowAction from './SC11-No-Show-Action'

type DiaryView = 'day' | 'week'

const OUT_COLUMNS = ['Booking', 'Customer', 'Tools', 'Where it stands', 'Action']
const BACK_COLUMNS = ['Hire', 'Customer', 'Tools', 'Due back', 'Where it stands']

export default function BranchDiary() {
  const { branch, setBranchCode } = useSession()
  const [view, setView] = useState<DiaryView>('day')
  const [anchor, setAnchor] = useState(TODAY)
  const [noShows, setNoShows] = useState<ReadonlySet<string>>(new Set())
  const [confirming, setConfirming] = useState<string | null>(null)

  const step = view === 'day' ? 1 : 7
  const collections = desk.collectionsOn(anchor, branch.code)
  const returns = desk.returnsOn(anchor, branch.code)
  const stillOut = anchor === TODAY ? desk.overdueReturns(branch.code) : []

  function markNoShow(reservationId: string) {
    setNoShows((current) => new Set(current).add(reservationId))
    setConfirming(null)
  }

  function undoNoShow(reservationId: string) {
    setNoShows((current) => {
      const next = new Set(current)
      next.delete(reservationId)
      return next
    })
  }

  return (
    <div>
      <PageHeader
        screenId="SC-11"
        title="Branch diary"
        subtitle={`What goes out and what comes back at ${branch.name}. ${
          view === 'day' ? formatDate(anchor) : `Week of ${formatDate(desk.startOfWeek(anchor))}`
        }.`}
        actions={
          <Link to="/counter/booking" className="btn-primary">
            Add a booking
          </Link>
        }
      />

      <div className="mb-lg flex flex-wrap items-end gap-md">
        <div role="group" aria-label="Day or week" className="flex gap-sm">
          {(['day', 'week'] as DiaryView[]).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={view === option}
              onClick={() => setView(option)}
              className={
                view === option ? 'btn bg-accent font-semibold text-accent-ink' : 'btn-secondary'
              }
            >
              {option === 'day' ? 'One day' : 'Whole week'}
            </button>
          ))}
        </div>

        <div className="flex gap-sm">
          <button
            type="button"
            onClick={() => setAnchor(desk.addDays(anchor, -step))}
            className="btn-secondary px-md"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">
              {view === 'day' ? 'Previous day' : 'Previous week'}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setAnchor(desk.addDays(anchor, step))}
            className="btn-secondary px-md"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">{view === 'day' ? 'Next day' : 'Next week'}</span>
          </button>
          <button type="button" onClick={() => setAnchor(TODAY)} className="btn-secondary">
            <CalendarCheck className="h-4 w-4" aria-hidden="true" />
            Back to today
          </button>
        </div>

        <div className="min-w-[12rem]">
          <Field label="Branch" htmlFor="diary-branch">
            <select
              id="diary-branch"
              className="field-input cursor-pointer"
              value={branch.code}
              onChange={(event) => setBranchCode(event.target.value as BranchCode)}
            >
              {branches.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </div>

      {view === 'week' ? (
        <DiaryWeek
          anchor={anchor}
          scope={branch.code}
          noShows={noShows}
          onOpenDay={(day) => {
            setAnchor(day)
            setView('day')
          }}
        />
      ) : (
        <div className="flex flex-col gap-lg">
          {stillOut.length > 0 && (
            <Notice tone="error" title={`${stillOut.length} hire still out from an earlier day`}>
              <p>
                {stillOut
                  .map(
                    (entry) =>
                      `${entry.customer.name}, due back ${formatDate(entry.dueOn)}, ${entry.daysLate} days late`,
                  )
                  .join('. ')}
                . Work through these on the overdue list.
              </p>
              <Link to="/counter/overdue" className="btn-secondary mt-sm">
                Open the overdue list
              </Link>
            </Notice>
          )}

          <Card title={`Going out, ${desk.weekdayName(anchor)} ${formatDate(anchor)}`}>
            {collections.length === 0 ? (
              <EmptyState
                title="Nothing goes out on this day"
                body="Use the arrows to look at another day, or add a booking."
              />
            ) : (
              <DataTable caption="Bookings due for collection" columns={OUT_COLUMNS}>
                {collections.map((entry) => {
                  const marked = noShows.has(entry.reservation.id)
                  const missed = marked || entry.reservation.status === 'NO_SHOW'
                  const collected = entry.rental !== undefined
                  return (
                    <tr key={entry.key}>
                      <td className="td font-mono">{entry.reservation.reference}</td>
                      <td className="td">
                        {entry.customer.name}
                        <span className="block font-mono text-xs text-slate-soft">
                          {entry.customer.phone}
                        </span>
                      </td>
                      <td className="td">{entry.headline}</td>
                      <td className="td">
                        {missed ? (
                          <StatusPill status="NO_SHOW" label="Did not arrive" />
                        ) : entry.rental ? (
                          <StatusPill
                            status="COLLECTED"
                            label={`Handed over ${formatDateTime(entry.rental.collectedAt).slice(-5)}`}
                          />
                        ) : (
                          <StatusPill
                            status={entry.reservation.status}
                            label="Waiting for collection"
                          />
                        )}
                      </td>
                      <td className="td">
                        <NoShowAction
                          reservationId={entry.reservation.id}
                          reference={entry.reservation.reference}
                          startDate={entry.reservation.startDate}
                          anchor={anchor}
                          collected={collected}
                          markedHere={marked}
                          recordedInFixture={entry.reservation.status === 'NO_SHOW'}
                          confirming={confirming === entry.reservation.id}
                          onAsk={() => setConfirming(entry.reservation.id)}
                          onCancel={() => setConfirming(null)}
                          onConfirm={() => markNoShow(entry.reservation.id)}
                          onUndo={() => undoNoShow(entry.reservation.id)}
                        />
                      </td>
                    </tr>
                  )
                })}
              </DataTable>
            )}
          </Card>

          <Card title={`Coming back, ${desk.weekdayName(anchor)} ${formatDate(anchor)}`}>
            {returns.length === 0 ? (
              <EmptyState
                title="Nothing is due back on this day"
                body="Returns show on the day the hire ends, whether or not it has been collected yet."
              />
            ) : (
              <DataTable caption="Hires due back" columns={BACK_COLUMNS}>
                {returns.map((entry) => (
                  <tr key={entry.key}>
                    <td className="td font-mono">
                      {entry.rental?.reference ?? entry.reservation.reference}
                    </td>
                    <td className="td">{entry.customer.name}</td>
                    <td className="td">{entry.headline}</td>
                    <td className="td whitespace-nowrap">{formatDate(entry.dueOn)}</td>
                    <td className="td">
                      {entry.overdue ? (
                        <StatusPill status="OVERDUE" label={`${entry.daysLate} days late`} />
                      ) : entry.collected ? (
                        <StatusPill status="OPEN" label="Out with the customer" />
                      ) : (
                        <StatusPill status="CONFIRMED" label="Not collected yet" />
                      )}
                    </td>
                  </tr>
                ))}
              </DataTable>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
