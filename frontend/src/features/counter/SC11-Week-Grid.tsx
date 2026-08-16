/**
 * The week at a glance, for SC-11.
 *
 * The paper diary is a book of days, so the week was something the branch
 * manager had to assemble in their head by flicking pages. Here it is one
 * screen: seven days, what goes out, what comes back, and which day is
 * busy enough to need a second pair of hands.
 */

import { ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import { TODAY } from '../../shared/fixtures'
import { formatDateShort } from '../../shared/format'
import type { BranchScope } from './counter-desk-data'
import * as desk from './counter-desk-data'

export default function DiaryWeek({
  anchor,
  scope,
  noShows,
  onOpenDay,
}: {
  /** Any date inside the week being shown. */
  anchor: string
  scope: BranchScope
  /** Reservation ids marked as a no-show during this session. */
  noShows: ReadonlySet<string>
  onOpenDay: (dateIso: string) => void
}) {
  const days = desk.weekDays(anchor)

  return (
    <ul className="grid gap-md sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
      {days.map((day) => {
        const collections = desk.collectionsOn(day, scope)
        const returns = desk.returnsOn(day, scope)
        const isToday = day === TODAY
        const quiet = collections.length === 0 && returns.length === 0

        return (
          <li key={day}>
            <button
              type="button"
              onClick={() => onOpenDay(day)}
              className={`card flex h-full w-full cursor-pointer flex-col gap-sm p-md text-left transition-shadow duration-200 hover:shadow-raised ${
                isToday ? 'ring-2 ring-accent' : ''
              }`}
            >
              <span className="flex items-baseline justify-between gap-sm">
                <span className="text-sm font-semibold text-ink">
                  {desk.weekdayName(day)} {formatDateShort(day)}
                </span>
                {isToday && (
                  <span className="rounded bg-accent px-xs py-xs text-xs font-semibold text-accent-ink">
                    Today
                  </span>
                )}
              </span>

              {quiet ? (
                <span className="text-sm text-slate-soft">Nothing booked</span>
              ) : (
                <span className="flex flex-col gap-sm">
                  {collections.map((entry) => {
                    const missed =
                      entry.reservation.status === 'NO_SHOW' || noShows.has(entry.reservation.id)
                    return (
                      <span
                        key={`out-${entry.key}`}
                        className="flex items-start gap-xs text-sm text-ink"
                      >
                        <ArrowUpRight
                          className="mt-0.5 h-4 w-4 shrink-0 text-status-due"
                          aria-hidden="true"
                        />
                        <span className="min-w-0">
                          <span className="block truncate">{entry.customer.name}</span>
                          <span className="block text-xs text-slate-soft">
                            {missed
                              ? 'Out, did not arrive'
                              : `Out, ${entry.units} ${entry.units === 1 ? 'unit' : 'units'}`}
                          </span>
                        </span>
                      </span>
                    )
                  })}

                  {returns.map((entry) => (
                    <span
                      key={`back-${entry.key}`}
                      className="flex items-start gap-xs text-sm text-ink"
                    >
                      <ArrowDownLeft
                        className="mt-0.5 h-4 w-4 shrink-0 text-status-onhire"
                        aria-hidden="true"
                      />
                      <span className="min-w-0">
                        <span className="block truncate">{entry.customer.name}</span>
                        <span className="block text-xs text-slate-soft">
                          {entry.overdue
                            ? `Back, ${entry.daysLate} ${entry.daysLate === 1 ? 'day' : 'days'} late`
                            : 'Back'}
                        </span>
                      </span>
                    </span>
                  ))}
                </span>
              )}

              <span className="mt-auto pt-sm text-xs font-medium text-slate-soft">
                {collections.length} out, {returns.length} back
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
