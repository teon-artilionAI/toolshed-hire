/**
 * Finding a tool to add to a counter booking, on SC-13.
 *
 * The list is the availability search, narrowed to the branch the assistant
 * works at, so it holds only the models that are free there for every day of
 * the period. Typing narrows it by the tool or the make, a moment after the
 * last key. Every row says where it is free, in words and not by colour.
 *
 * Nothing here is a price. The server prices the booking once the tools are
 * chosen.
 */

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Plus } from 'lucide-react'
import { MIN_SEARCH_LENGTH } from '../../shared/api/catalogue'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import type { AvailabilityPage, ModelSummary } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import type { QueryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { StatusPill } from '../../shared/ui'
import { TextInput } from './counter-fields'
import { describeCounterFailure } from './counter-refusal'
import type { CounterBranch } from './work-branch-gate'

/** How many models a page of the finder holds. */
const FINDER_PAGE_SIZE = 6

/** How long the search waits after the last key before it runs. */
const FINDER_DEBOUNCE_MS = 300

const FIRST_PAGE = 1

function statusLine(phase: QueryPhase, data: AvailabilityPage | undefined, branch: CounterBranch): string {
  if (phase === 'loading') return `Looking for what is free at ${branch.name}.`
  if (phase !== 'ready' || !data) return 'The tools did not load.'
  if (data.total === 0) return `Nothing that matches is free at ${branch.name} for these dates.`
  return `${data.total} ${data.total === 1 ? 'model is' : 'models are'} free at ${branch.name} for these dates.`
}

export function ModelFinder({
  branch,
  period,
  chosenSlugs,
  disabled,
  onAdd,
}: {
  branch: CounterBranch
  /** Null while the dates cannot be asked about. */
  period: { from: string; to: string } | null
  /** The models already on the booking. */
  chosenSlugs: readonly string[]
  disabled: boolean
  onAdd: (model: ModelSummary) => void
}) {
  const [draft, setDraft] = useState('')
  const [searched, setSearched] = useState('')
  const [page, setPage] = useState(FIRST_PAGE)

  useEffect(() => {
    const typed = draft.trim()
    if (typed === searched) return
    const timer = window.setTimeout(() => {
      setSearched(typed)
      setPage(FIRST_PAGE)
    }, FINDER_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [draft, searched])

  const available = useQuery({
    ...catalogueQueries.availability({
      from: period?.from ?? '',
      to: period?.to ?? '',
      q: searched.length >= MIN_SEARCH_LENGTH ? searched : undefined,
      branch: branch.code,
      page,
      pageSize: FINDER_PAGE_SIZE,
    }),
    enabled: period !== null,
  })
  const phase = queryPhase(available)
  const data = available.data
  const refusal = phase === 'failed' ? describeCounterFailure(available.error) : null

  return (
    <div>
      <div className="max-w-xl">
        <TextInput
          id="finder-search"
          type="search"
          label="Find a tool"
          help={`Type ${MIN_SEARCH_LENGTH} letters or more of the tool or the make, or leave it empty to see everything free here.`}
          value={draft}
          onChange={setDraft}
          placeholder="Breaker, Bosch, mixer"
          autoComplete="off"
        />
      </div>

      <section aria-label="Tools free at this branch" className="mt-md">
        {period === null ? (
          <p className="text-sm text-slate-soft" role="status">
            Choose the dates first. The list shows what is free for them.
          </p>
        ) : (
          <p className="mb-sm text-sm text-slate-soft" role="status">
            {statusLine(phase, data, branch)}
          </p>
        )}

        {period !== null && phase === 'loading' && <LoadingState shape="rows" count={2} />}

        {refusal !== null && refusal.kind === 'fault' && (
          <ErrorState what="the tools" error={refusal.error} onRetry={() => void available.refetch()} />
        )}
        {refusal !== null && refusal.kind !== 'fault' && (
          <p className="text-sm text-status-overdue">{refusal.detail}</p>
        )}

        {phase === 'ready' && data && data.items.length > 0 && (
          <>
            <ul className="flex flex-col gap-sm" aria-busy={available.isFetching}>
              {data.items.map(({ model, branches }) => {
                const onBooking = chosenSlugs.includes(model.slug)
                const here = branches.find((answer) => answer.branchCode === branch.code)
                return (
                  <li
                    key={model.slug}
                    className="flex flex-wrap items-center justify-between gap-sm rounded border border-line p-sm"
                  >
                    <div className="min-w-0">
                      <p className="break-words text-sm font-medium text-ink">{model.name}</p>
                      <p className="text-sm text-slate-soft">
                        {model.manufacturer}, {model.categoryName}
                      </p>
                      {here?.available && (
                        <div className="mt-xs">
                          <StatusPill status="AVAILABLE" label={`Free at ${branch.name}`} />
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      className="btn-secondary px-md"
                      disabled={disabled || onBooking}
                      onClick={() => onAdd(model)}
                    >
                      {onBooking ? (
                        <Check className="h-4 w-4 shrink-0" aria-hidden="true" />
                      ) : (
                        <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
                      )}
                      {onBooking ? 'On the booking' : 'Add'}{' '}
                      <span className="sr-only">{model.name}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
            <Pagination
              label="Pages of tools"
              page={data.page}
              pageSize={data.pageSize}
              total={data.total}
              onPageChange={setPage}
            />
          </>
        )}
      </section>
    </div>
  )
}
