/**
 * The units that match a search, on SC-17.
 *
 * The list is the server's. It matches the asset tag and the model name at
 * every branch and decides what a page holds. Nothing is asked until two
 * characters have been typed, which is the shortest search the server takes.
 *
 * Six columns do not fit across a phone, and a table that has to be scrolled
 * sideways hides the state of every unit. So below the `sm` width the table is
 * drawn as one block for each unit, with every value on a line of its own and
 * its heading beside it. It is the same table either way, and each part states
 * its role, because changing how a table is displayed can make a browser stop
 * reporting it as one.
 *
 * Each unit says its state in words as well as colour. A unit on hire says the
 * day it is due back and the hire it is on, and any other unit says it is not
 * on hire. The line above the list is a polite status, so a person who cannot
 * see the list change still hears that it did.
 */

import type { ReactNode, RefObject } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapPin } from 'lucide-react'
import type { LocatedUnit, LocatorPage } from '../../shared/api/contract'
import { locatorQueries } from '../../shared/api/counter-queries'
import { MIN_LOCATOR_SEARCH_LENGTH } from '../../shared/api/locator'
import { queryPhase } from '../../shared/api/query-phase'
import type { QueryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { formatDate } from '../../shared/format'
import Pagination from '../../shared/pagination'
import { EmptyState, StatusPill } from '../../shared/ui'
import { ASSET_STATUS_LABEL, CONDITION_GRADE_LABEL, countOf } from './counter-labels'

/** How many units a page of results holds. The API's own default. */
const LOCATOR_PAGE_SIZE = 20

/** Pages are counted from one. */
export const FIRST_PAGE = 1

/** Skeleton blocks to draw while a search runs. */
const RESULT_SKELETON_COUNT = 3

const COLUMN = {
  tag: 'Asset tag',
  model: 'Model',
  branch: 'Branch',
  status: 'State',
  grade: 'Condition',
  dueBack: 'Due back',
} as const

/** What every cell shares. A table cell from `sm` up, and tighter on a phone. */
const CELL_BASE = 'td px-0 py-xs text-left sm:table-cell sm:px-md sm:py-sm'

/** A cell that shows the name of its column beside its value on a phone. */
const LABELLED_CELL = `${CELL_BASE} flex items-baseline justify-between gap-md`

function statusLine(phase: QueryPhase, searched: string, data: LocatorPage | undefined): string {
  if (searched.length < MIN_LOCATOR_SEARCH_LENGTH) {
    return `Type ${MIN_LOCATOR_SEARCH_LENGTH} characters or more to search.`
  }
  if (phase === 'loading') return 'Searching every branch.'
  if (phase !== 'ready' || !data) return 'The search did not work.'
  if (data.total === 0) return `Nothing on the fleet matches "${searched}".`
  return `${countOf(data.total, 'unit matches', 'units match')} "${searched}", across every branch.`
}

/** The name of a column, shown only where the headings are not. */
function ColumnName({ children }: { children: ReactNode }) {
  return <span className="shrink-0 text-sm text-slate-soft sm:hidden">{children}</span>
}

function UnitRow({ unit }: { unit: LocatedUnit }) {
  return (
    <tr role="row" className="block px-md py-sm sm:table-row">
      <th role="rowheader" scope="row" className={`${CELL_BASE} block whitespace-nowrap font-mono font-medium text-ink`}>
        {unit.assetTag}
      </th>
      <td role="cell" className={LABELLED_CELL}>
        <ColumnName>{COLUMN.model}</ColumnName>
        <span className="min-w-0 break-words text-right text-ink sm:text-left">
          {unit.modelName}
          <span className="block text-xs text-slate-soft">{unit.categoryName}</span>
        </span>
      </td>
      <td role="cell" className={LABELLED_CELL}>
        <ColumnName>{COLUMN.branch}</ColumnName>
        <span className="flex items-center gap-xs text-ink">
          <MapPin className="h-4 w-4 shrink-0 text-slate-faint" aria-hidden="true" />
          {unit.branchName}
        </span>
      </td>
      <td role="cell" className={LABELLED_CELL}>
        <ColumnName>{COLUMN.status}</ColumnName>
        <StatusPill status={unit.status} label={ASSET_STATUS_LABEL[unit.status]} />
      </td>
      <td role="cell" className={LABELLED_CELL}>
        <ColumnName>{COLUMN.grade}</ColumnName>
        <span className="text-right text-ink sm:text-left">{CONDITION_GRADE_LABEL[unit.conditionGrade]}</span>
      </td>
      <td role="cell" className={LABELLED_CELL}>
        <ColumnName>{COLUMN.dueBack}</ColumnName>
        {unit.dueBackOn === null ? (
          <span className="text-right text-slate-soft sm:text-left">Not on hire</span>
        ) : (
          <span className="tabular text-right text-ink sm:text-left">
            {formatDate(unit.dueBackOn)}
            {unit.rentalReference !== null && (
              <span className="block font-mono text-xs text-slate-soft">{unit.rentalReference}</span>
            )}
          </span>
        )}
      </td>
    </tr>
  )
}

function UnitTable({ units }: { units: LocatedUnit[] }) {
  return (
    <div className="table-wrap">
      <table role="table" className="block w-full border-collapse sm:table">
        <caption className="sr-only">Every unit matching the search, with its branch and its state</caption>
        <thead role="rowgroup" className="hidden border-b border-line bg-muted sm:table-header-group">
          <tr role="row">
            {Object.values(COLUMN).map((column) => (
              <th key={column} role="columnheader" scope="col" className="th">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup" className="block divide-y divide-line sm:table-row-group">
          {units.map((unit) => (
            <UnitRow key={unit.assetTag} unit={unit} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function UnitResults({
  searched,
  page,
  regionRef,
  onPage,
}: {
  /** What was last searched for, trimmed. */
  searched: string
  page: number
  regionRef: RefObject<HTMLElement | null>
  onPage: (page: number) => void
}) {
  const searchable = searched.length >= MIN_LOCATOR_SEARCH_LENGTH
  const results = useQuery({
    ...locatorQueries.search({ q: searched, page, pageSize: LOCATOR_PAGE_SIZE }),
    enabled: searchable,
  })
  const phase = queryPhase(results)
  const data = results.data

  return (
    <section ref={regionRef} tabIndex={-1} aria-label="Units found">
      <p className="mb-md text-sm text-slate-soft" role="status">
        {statusLine(phase, searched, data)}
      </p>

      {searchable && phase === 'loading' && <LoadingState shape="rows" count={RESULT_SKELETON_COUNT} />}

      {searchable && phase === 'failed' && (
        <ErrorState what="the units" error={results.error} onRetry={() => void results.refetch()} />
      )}

      {searchable && phase === 'ready' && data && data.items.length === 0 && (
        <div className="card">
          <EmptyState
            title={data.total > 0 ? 'That page is past the end of the results' : 'Nothing on the fleet matches that'}
            body={
              data.total > 0
                ? 'Go back to the first page of the results.'
                : 'Check the tag against the plate on the unit, or search by part of the model name instead.'
            }
            action={
              data.total > 0 ? (
                <button type="button" className="btn-secondary px-md" onClick={() => onPage(FIRST_PAGE)}>
                  Go to the first page
                </button>
              ) : undefined
            }
          />
        </div>
      )}

      {searchable && phase === 'ready' && data && data.items.length > 0 && (
        <div aria-busy={results.isFetching}>
          <UnitTable units={data.items} />
          <Pagination
            label="Unit result pages"
            page={data.page}
            pageSize={data.pageSize}
            total={data.total}
            onPageChange={onPage}
          />
        </div>
      )}
    </section>
  )
}
