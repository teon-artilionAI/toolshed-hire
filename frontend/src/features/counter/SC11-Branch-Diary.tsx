/**
 * SC-11 Branch Diary.
 *
 * This screen replaces the paper book the branches run on, so it does what the
 * book does and then what the book cannot. It shows a day, or a whole week from
 * Monday, of what goes out and what comes back at the branch the person works
 * at. Previous and next move a day or a week, and one press goes back to today.
 * A no show is recorded at the moment it happens and not in a margin.
 *
 * The day and the view live in the address, so a reload or a link brings the
 * same page back. Today in day view is the plain address, so a tab left open
 * overnight shows the new day after a reload. The address is user input, so a
 * date that is not a day on the calendar falls back to today.
 *
 * The diary is one request for the days on the screen, and the server's lazy
 * sweep runs before it answers. The branch comes from work-branch.ts through
 * the gate, so counter staff see their own branch and an administrator the one
 * they chose.
 */

import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarCheck, ChevronLeft, ChevronRight } from 'lucide-react'
import type { BranchDiary as Diary } from '../../shared/api/contract'
import { overviewQueries } from '../../shared/api/counter-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { todayInBranchTime } from '../../shared/today'
import { EmptyState, PageHeader } from '../../shared/ui'
import { NEW_BOOKING_PATH } from './counter-links'
import { DAYS_IN_WEEK, addDays, dayName, readIsoDate, startOfWeek } from './diary-dates'
import { DiaryDaySection } from './SC11-Diary-Day'
import { WorkBranchGate } from './work-branch-gate'
import type { CounterBranch } from './work-branch-gate'

type DiaryView = 'day' | 'week'

const VIEWS: readonly DiaryView[] = ['day', 'week']

const VIEW_LABEL: Record<DiaryView, string> = { day: 'One day', week: 'Whole week' }

const DATE_PARAMETER = 'date'
const VIEW_PARAMETER = 'view'

/** Skeleton blocks to draw while the diary loads. */
const DIARY_SKELETON_COUNT = 2

function readView(value: string | null): DiaryView {
  return VIEWS.find((view) => view === value) ?? 'day'
}

/** What the screen is showing, in words, for the status line. */
function showing(view: DiaryView, date: string, branchName: string): string {
  return view === 'day'
    ? `${dayName(date)} at ${branchName}.`
    : `The week starting ${dayName(startOfWeek(date))} at ${branchName}.`
}

function isEmpty(diary: Diary): boolean {
  return diary.days.every((day) => day.collections.length === 0 && day.returns.length === 0)
}

function DiaryDesk({ branch }: { branch: CounterBranch }) {
  const [params, setParams] = useSearchParams()
  const today = todayInBranchTime()
  const view = readView(params.get(VIEW_PARAMETER))
  const date = readIsoDate(params.get(DATE_PARAMETER)) ?? today
  const step = view === 'day' ? 1 : DAYS_IN_WEEK
  const from = view === 'day' ? date : startOfWeek(date)
  const diary = useQuery(overviewQueries.diary({ branchCode: branch.code, from, days: step }))
  const phase = queryPhase(diary)
  const data = diary.data

  /** Write the day and the view to the address. A default is left out. */
  function show(nextDate: string, nextView: DiaryView) {
    const written = new URLSearchParams()
    if (nextDate !== today) written.set(DATE_PARAMETER, nextDate)
    if (nextView !== 'day') written.set(VIEW_PARAMETER, nextView)
    setParams(written)
  }

  const unit = view === 'day' ? 'day' : 'week'
  return (
    <>
      <div className="mb-lg flex flex-wrap items-center gap-md">
        <div role="group" aria-label="Show one day or a whole week" className="flex flex-wrap gap-sm">
          {VIEWS.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={view === option}
              onClick={() => show(date, option)}
              className={view === option ? 'btn bg-accent font-semibold text-accent-ink' : 'btn-secondary'}
            >
              {VIEW_LABEL[option]}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-sm">
          <button type="button" className="btn-secondary px-md" onClick={() => show(addDays(date, -step), view)}>
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">Previous {unit}</span>
          </button>
          <button type="button" className="btn-secondary px-md" onClick={() => show(addDays(date, step), view)}>
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">Next {unit}</span>
          </button>
          <button type="button" className="btn-secondary px-md" onClick={() => show(today, view)}>
            <CalendarCheck className="h-4 w-4" aria-hidden="true" />
            Back to today
          </button>
        </div>
      </div>

      <p role="status" className="mb-md text-sm text-slate-soft">
        {showing(view, date, data?.branchName ?? branch.name)}
      </p>

      {phase === 'failed' ? (
        <ErrorState what="the diary" error={diary.error} onRetry={() => void diary.refetch()} />
      ) : data === undefined ? (
        <LoadingState label="Loading the diary" shape="rows" count={DIARY_SKELETON_COUNT} />
      ) : isEmpty(data) ? (
        <div className="card">
          <EmptyState
            title={view === 'day' ? 'Nothing goes out or comes back on this day' : 'Nothing goes out or comes back this week'}
            body={`Nothing is booked to be collected from ${data.branchName} and no hire is due back there. Use the arrows to look at another ${unit}.`}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-lg" aria-busy={diary.isFetching}>
          {data.days.map((day) => (
            <DiaryDaySection
              key={day.date}
              day={day}
              today={today}
              onOpenDay={view === 'week' ? (opened) => show(opened, 'day') : undefined}
            />
          ))}
        </div>
      )}
    </>
  )
}

export default function BranchDiary() {
  return (
    <>
      <PageHeader
        screenId="SC-11"
        title="Branch diary"
        subtitle="What goes out and what comes back at your branch, a day or a week at a time."
        actions={
          <Link to={NEW_BOOKING_PATH} className="btn-primary">
            Add a booking
          </Link>
        }
      />
      <WorkBranchGate>{(branch) => <DiaryDesk branch={branch} />}</WorkBranchGate>
    </>
  )
}
