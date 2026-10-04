/**
 * Everything on SC-22 under the controls, for each state the report can be in.
 *
 * While the report is worked out there is a skeleton. A refusal, which is the
 * server saying no to the period or a filter, puts each message under its
 * control above and lists here any it could not place. Any other failure is
 * the shared error state with the way to try again. A loaded report shows the
 * totals, the two definitions, the rows of the page with the CSV beside them,
 * the chart of those rows and the page controls.
 *
 * The line at the top is a polite status, so a person who cannot see the
 * figures change still hears that they did. Moving to another page moves
 * focus to the top of the figures, so a keyboard user reads the new page from
 * its start.
 */

import { useRef } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import type { UtilisationReport } from '../../shared/api/contract'
import { isRefusal } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import type { QueryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { EmptyState, Notice } from '../../shared/ui'
import { countOf } from '../counter/counter-labels'
import { FIRST_PAGE, csvQueryFor } from './report-address'
import type { ReportFilters } from './report-address'
import { GROUPING_PHRASE, periodWords } from './report-labels'
import ReportDownload from './ReportDownload'
import ReportNotes from './ReportNotes'
import ReportTable from './ReportTable'
import ReportTotals from './ReportTotals'
import UtilisationChart from './SC22-Utilisation-Chart'

/** Skeleton blocks to draw while the report is worked out. */
const SKELETON_TILES = 4

function statusLine(phase: QueryPhase, refused: boolean, report: UtilisationReport | undefined): string {
  if (phase === 'loading') return 'Working out the figures.'
  if (refused) return 'The report was not worked out for that choice.'
  if (phase !== 'ready' || report === undefined) return 'The report could not be worked out.'
  return `${countOf(report.total, 'row', 'rows')} ${GROUPING_PHRASE[report.groupBy]}, ${periodWords(report.from, report.to)}.`
}

function LoadedReport({
  report,
  filters,
  onPage,
  onClearFilters,
}: {
  report: UtilisationReport
  filters: ReportFilters
  onPage: (page: number) => void
  onClearFilters: () => void
}) {
  const filtered = filters.branchCode !== null || filters.categorySlug !== null
  const pastTheEnd = report.items.length === 0 && report.total > 0
  return (
    <>
      <ReportTotals totals={report.totals} />
      <ReportNotes definitions={report.definitions} />
      <section aria-labelledby="report-rows-heading">
        <div className="mb-md flex flex-wrap items-start justify-between gap-md">
          <h2 id="report-rows-heading" className="text-lg font-semibold text-ink">
            Broken down {GROUPING_PHRASE[report.groupBy]}
          </h2>
          <ReportDownload query={csvQueryFor(filters)} />
        </div>
        {report.items.length === 0 ? (
          <div className="card">
            <EmptyState
              title={pastTheEnd ? 'That page is past the end of the report' : 'Nothing matches that choice'}
              body={
                pastTheEnd
                  ? 'Go back to the first page of the report.'
                  : 'No unit was in the fleet for that period with that branch and category. Choose another period or widen the filters.'
              }
              action={
                pastTheEnd ? (
                  <button type="button" className="btn-secondary px-md" onClick={() => onPage(FIRST_PAGE)}>
                    Go to the first page
                  </button>
                ) : filtered ? (
                  <button type="button" className="btn-secondary px-md" onClick={onClearFilters}>
                    Show every branch and category
                  </button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <>
            <ReportTable
              rows={report.items}
              groupBy={report.groupBy}
              caption={`Utilisation and gross contribution ${GROUPING_PHRASE[report.groupBy]}, highest gross contribution first, page ${report.page}`}
            />
            <UtilisationChart rows={report.items} groupBy={report.groupBy} />
          </>
        )}
        <Pagination
          label="Report pages"
          page={report.page}
          pageSize={report.pageSize}
          total={report.total}
          onPageChange={onPage}
        />
      </section>
    </>
  )
}

export default function ReportResults({
  report,
  filters,
  otherMessages,
  onPage,
  onClearFilters,
}: {
  report: UseQueryResult<UtilisationReport>
  filters: ReportFilters
  /** What the server refused about a value that has no control on the screen. */
  otherMessages: readonly string[]
  onPage: (page: number) => void
  onClearFilters: () => void
}) {
  const regionRef = useRef<HTMLElement>(null)
  const phase = queryPhase(report)
  const refused = phase === 'failed' && isRefusal(report.error)
  const data = report.data

  function goToPage(page: number) {
    onPage(page)
    regionRef.current?.focus()
  }

  return (
    <section ref={regionRef} tabIndex={-1} aria-label="The figures">
      <p role="status" className="mb-md text-sm text-slate-soft">
        {statusLine(phase, refused, data)}
      </p>

      {phase === 'loading' && <LoadingState shape="tiles" count={SKELETON_TILES} />}

      {refused && (
        <Notice tone="error" title="The report cannot be worked out for that choice">
          <p>Check the messages under the controls above and change what they point to.</p>
          {otherMessages.length > 0 && (
            <ul className="mt-xs list-disc pl-lg">
              {otherMessages.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          )}
        </Notice>
      )}

      {phase === 'failed' && !refused && (
        <ErrorState what="the report" error={report.error} onRetry={() => void report.refetch()} />
      )}

      {phase === 'ready' && data !== undefined && (
        <div aria-busy={report.isFetching}>
          <LoadedReport report={data} filters={filters} onPage={goToPage} onClearFilters={onClearFilters} />
        </div>
      )}
    </section>
  )
}
