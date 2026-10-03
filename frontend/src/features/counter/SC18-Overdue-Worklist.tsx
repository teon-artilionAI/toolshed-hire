/**
 * SC-18 Overdue and Late Fee Worklist.
 *
 * The morning job. Every hire at the branch the person works at with a unit
 * out past its due date, read from `GET /api/rentals?overdueOnly=true`, most
 * overdue first and twenty to a page. Each hire says who has it and how to
 * reach them, the day it was due back, and each unit still out with its days
 * late and its late fee so far, and links to its return. Every figure is the
 * server's, and the browser adds nothing up.
 *
 * Under the list is the escalation queue, the units more than fourteen days
 * late, each of which can be recorded as lost. What a loss did is said above
 * the lists in a notice that takes focus, so it stays on the screen when the
 * list is read again and the hire moves on it.
 *
 * The page lives in the address, so a reload keeps it. A page that is not a
 * whole number from one falls back to the first.
 */

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { Rental, RentalPage } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import type { QueryPhase } from '../../shared/api/query-phase'
import { rentalQueries } from '../../shared/api/rental-queries'
import { RENTAL_PAGE_SIZE } from '../../shared/api/rentals'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { isNegativeMoney, money, unsignedMoney } from '../../shared/format'
import Pagination from '../../shared/pagination'
import { Card, EmptyState, Notice, PageHeader } from '../../shared/ui'
import { CHARGE_TYPE_LABEL, RENTAL_STATUS_LABEL, countOf } from './counter-labels'
import { EscalationQueue, OverdueHire } from './SC18-Overdue-Hire'
import type { LossOutcome } from './SC18-Loss-Action'
import { WorkBranchGate } from './work-branch-gate'
import type { CounterBranch } from './work-branch-gate'

const FIRST_PAGE = 1
const PAGE_PARAMETER = 'page'

/** Skeleton blocks to draw while the list loads. */
const LIST_SKELETON_COUNT = 3

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

function statusLine(phase: QueryPhase, data: RentalPage | undefined, branch: CounterBranch): string {
  if (phase === 'loading') return `Reading the overdue hires at ${branch.name}.`
  if (phase !== 'ready' || !data) return 'The overdue hires did not load.'
  if (data.total === 0) return `Nothing is overdue at ${branch.name}.`
  return `${countOf(data.total, 'hire is', 'hires are')} overdue at ${branch.name}, most overdue first.`
}

/**
 * Where the money stands after a loss. The server works the balance out when
 * it settles the deposit, which waits for the last unit, so while any unit is
 * still out its balance due is nought and says nothing yet.
 */
function balanceAfterLoss(rental: Rental): string {
  if (rental.settlementWaitingOn === 'ITEMS_OUT') {
    return 'The deposit is settled, and any balance worked out, once the last unit is back.'
  }
  return `Balance due ${money(rental.balanceDue)}.`
}

/** What a loss did, from the hire the server answered with. */
function LossRecorded({ outcome }: { outcome: LossOutcome }) {
  const { rental, label, itemId } = outcome
  const charges = rental.charges.filter((charge) => charge.rentalItemId === itemId)
  return (
    <Notice tone="success" title={`${label} on ${rental.reference} is recorded as lost`}>
      <p>
        The hire is now {RENTAL_STATUS_LABEL[rental.status].toLowerCase()}. {balanceAfterLoss(rental)}
      </p>
      {charges.length > 0 && (
        <ul className="mt-xs flex flex-col gap-xs">
          {charges.map((charge) => (
            <li key={charge.id} className="tabular break-words">
              {CHARGE_TYPE_LABEL[charge.type]}. {charge.description}{' '}
              {isNegativeMoney(charge.amountIncVat)
                ? `${unsignedMoney(charge.amountIncVat)} back to the customer`
                : money(charge.amountIncVat)}
            </li>
          ))}
        </ul>
      )}
    </Notice>
  )
}

function OverdueAt({ branch }: { branch: CounterBranch }) {
  const [params, setParams] = useSearchParams()
  const page = readPage(params.get(PAGE_PARAMETER))
  const list = useQuery(
    rentalQueries.list({ branchCode: branch.code, overdueOnly: true, page, pageSize: RENTAL_PAGE_SIZE }),
  )
  const phase = queryPhase(list)
  const data = list.data
  const [recorded, setRecorded] = useState<LossOutcome | null>(null)
  const regionRef = useRef<HTMLElement>(null)
  const recordedRef = useRef<HTMLDivElement>(null)

  // A loss takes its question away, so focus goes to what it did.
  useEffect(() => {
    if (recorded !== null) recordedRef.current?.focus()
  }, [recorded])

  function goToPage(next: number) {
    const written = new URLSearchParams()
    if (next > FIRST_PAGE) written.set(PAGE_PARAMETER, String(next))
    setParams(written, { replace: true })
    // The new page replaces the list, so focus goes to the top of it.
    regionRef.current?.focus()
  }

  return (
    <div className="flex flex-col gap-lg">
      <div ref={recordedRef} tabIndex={-1} className="empty:hidden">
        {recorded !== null && <LossRecorded outcome={recorded} />}
      </div>

      <section ref={regionRef} tabIndex={-1} aria-label="Overdue hires">
        <p className="mb-md text-sm text-slate-soft" role="status">
          {statusLine(phase, data, branch)}
        </p>

        {phase === 'loading' && <LoadingState shape="rows" count={LIST_SKELETON_COUNT} />}

        {phase === 'failed' && (
          <ErrorState what="the overdue hires" error={list.error} onRetry={() => void list.refetch()} />
        )}

        {phase === 'ready' && data && data.items.length === 0 && (
          <div className="card">
            <EmptyState
              title={data.total > 0 ? 'That page is past the end of the list' : `Nothing is overdue at ${branch.name}`}
              body={
                data.total > 0
                  ? 'Go back to the first page of the overdue hires.'
                  : 'Every hire at this branch is back or still in date. Hires due back today are on the dashboard.'
              }
              action={
                data.total > 0 ? (
                  <button type="button" className="btn-secondary px-md" onClick={() => goToPage(FIRST_PAGE)}>
                    Go to the first page
                  </button>
                ) : undefined
              }
            />
          </div>
        )}

        {phase === 'ready' && data && data.items.length > 0 && (
          <div aria-busy={list.isFetching}>
            <Card>
              <ul aria-label={`Overdue hires at ${branch.name}`}>
                {data.items.map((rental) => (
                  <OverdueHire key={rental.id} rental={rental} />
                ))}
              </ul>
            </Card>
            <Pagination
              label="Overdue hire pages"
              page={data.page}
              pageSize={data.pageSize}
              total={data.total}
              onPageChange={goToPage}
            />
          </div>
        )}
      </section>

      {phase === 'ready' && data && data.items.length > 0 && (
        <EscalationQueue hires={data.items} onRecorded={setRecorded} />
      )}
    </div>
  )
}

export default function OverdueAndLateFeeWorklist() {
  return (
    <>
      <PageHeader
        screenId="SC-18"
        title="Overdue and late fees"
        subtitle="Every hire at your branch with a unit out past its due date, what each unit's late fee is today, and the units out long enough to record as lost."
      />
      <WorkBranchGate>{(branch) => <OverdueAt branch={branch} />}</WorkBranchGate>
    </>
  )
}
