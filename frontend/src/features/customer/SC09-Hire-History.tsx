/**
 * The hire history half of SC-09.
 *
 * The signed in customer's own hires, read from `GET /api/me/rentals`, newest
 * first and five to a page. Each hire says its reference, its branch, its dates
 * and its status in words, what was hired without any tag, every charge, and
 * where the deposit stands. Every figure is the server's.
 *
 * It has the shared loading and failed states, and an empty state for a
 * customer who has not collected anything yet. The page lives in the address,
 * so a reload keeps it. The line above the list is a polite status, so a person
 * who cannot see the list change still hears that it did.
 */

import { useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { RentalPage } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import type { QueryPhase } from '../../shared/api/query-phase'
import { rentalQueries } from '../../shared/api/rental-queries'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { Card, EmptyState } from '../../shared/ui'
import { HireHistoryEntry } from './hire-history-entry'
import { MY_RESERVATIONS_PATH } from './reservation-links'

/** How many hires a page of the history holds. It sits in a narrow column. */
export const HISTORY_PAGE_SIZE = 5

const FIRST_PAGE = 1
const PAGE_PARAMETER = 'page'

/** Skeleton blocks to draw while the history loads. */
const HISTORY_SKELETON_COUNT = 2

export const NO_HIRES_TITLE = 'No hires yet'

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

function statusLine(phase: QueryPhase, data: RentalPage | undefined): string {
  if (phase === 'loading') return 'Loading your hires.'
  if (phase !== 'ready' || !data) return 'Your hires did not load.'
  if (data.total === 0) return 'You have no hires yet.'
  return `${data.total} ${data.total === 1 ? 'hire' : 'hires'} on your account, newest first.`
}

export function HireHistory() {
  const [params, setParams] = useSearchParams()
  const page = readPage(params.get(PAGE_PARAMETER))
  const hires = useQuery(rentalQueries.mine({ page, pageSize: HISTORY_PAGE_SIZE }))
  const phase = queryPhase(hires)
  const data = hires.data
  const regionRef = useRef<HTMLElement>(null)

  function goToPage(next: number) {
    const written = new URLSearchParams()
    if (next > FIRST_PAGE) written.set(PAGE_PARAMETER, String(next))
    setParams(written, { replace: true })
    // The new page replaces the list, so focus goes to the top of it.
    regionRef.current?.focus()
  }

  return (
    <Card title="Hire history and charges">
      <section ref={regionRef} tabIndex={-1} aria-label="Your hires">
        <p className="mb-md text-sm text-slate-soft" role="status">
          {statusLine(phase, data)}
        </p>

        {phase === 'loading' && <LoadingState shape="rows" count={HISTORY_SKELETON_COUNT} />}

        {phase === 'failed' && (
          <ErrorState what="your hire history" error={hires.error} onRetry={() => void hires.refetch()} />
        )}

        {phase === 'ready' && data && data.items.length === 0 && (
          <EmptyState
            title={data.total > 0 ? 'That page is past the end of your hires' : NO_HIRES_TITLE}
            body={
              data.total > 0
                ? 'Go back to the first page of your hires.'
                : 'A hire appears here once you collect equipment from a branch, with its charges and what happened to your deposit. Your bookings are under My Hires.'
            }
            action={
              data.total > 0 ? (
                <button type="button" className="btn-secondary px-md" onClick={() => goToPage(FIRST_PAGE)}>
                  Go to the first page
                </button>
              ) : (
                <Link to={MY_RESERVATIONS_PATH} className="btn-secondary px-md">
                  See my bookings
                </Link>
              )
            }
          />
        )}

        {phase === 'ready' && data && data.items.length > 0 && (
          <div aria-busy={hires.isFetching}>
            <ul aria-label="Hires, newest first">
              {data.items.map((rental) => (
                <HireHistoryEntry key={rental.id} rental={rental} />
              ))}
            </ul>
            <Pagination
              label="Hire history pages"
              page={data.page}
              pageSize={data.pageSize}
              total={data.total}
              onPageChange={goToPage}
            />
          </div>
        )}
      </section>
    </Card>
  )
}
