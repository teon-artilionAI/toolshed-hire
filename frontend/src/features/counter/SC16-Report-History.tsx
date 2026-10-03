/**
 * The damage reports already filed against a unit, on SC-16.
 *
 * They are read from `GET /api/damage-reports?assetTag=`, newest first, with
 * the loading, failed and empty states of their own, so the form beside them
 * works while they load. A unit has few reports, so the first page is shown,
 * and when there are more the card says how many.
 *
 * When the owner moves a report on, the list shows the server's answer at once
 * and is read again, and a notice above it says what the move did. The notice
 * takes focus, because the buttons that were pressed may be gone.
 */

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { DamageReport } from '../../shared/api/contract'
import { damageQueries } from '../../shared/api/damage-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { Card, Notice } from '../../shared/ui'
import { countOf } from './counter-labels'
import { ReportEntry } from './SC16-Report-Entry'

const SKELETON_COUNT = 2

/** What a move on a report did, in words, from the report the server answered with. */
function movedInWords(report: DamageReport): { title: string; body: string } {
  if (report.status === 'UNDER_REPAIR') {
    return {
      title: `${report.reference} is sent for repair`,
      body: `${report.assetTag} is in the workshop and still cannot be booked.`,
    }
  }
  if (report.status === 'WRITTEN_OFF') {
    return { title: `${report.reference} is written off`, body: `${report.assetTag} is retired from the fleet.` }
  }
  return {
    title: `${report.reference} is resolved`,
    body: `${report.assetTag} goes back on the shelf, unless another report on it is still open.`,
  }
}

export function ReportHistory({ assetTag, ownerSignedIn }: { assetTag: string; ownerSignedIn: boolean }) {
  const reports = useQuery(damageQueries.forUnit(assetTag))
  const phase = queryPhase(reports)
  const data = reports.data
  const [moved, setMoved] = useState<DamageReport | null>(null)

  const movedRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (moved !== null) movedRef.current?.focus()
  }, [moved])

  const words = moved === null ? null : movedInWords(moved)
  return (
    <Card title="Already on this unit's record">
      <div ref={movedRef} tabIndex={-1} className="mb-md empty:hidden">
        {words !== null && (
          <Notice tone="success" title={words.title}>
            <p>{words.body}</p>
          </Notice>
        )}
      </div>
      {phase === 'failed' ? (
        <ErrorState what="the damage reports of this unit" error={reports.error} onRetry={() => void reports.refetch()} />
      ) : data === undefined ? (
        <LoadingState label="Loading the damage reports" shape="rows" count={SKELETON_COUNT} />
      ) : data.items.length === 0 ? (
        <p className="text-sm text-slate-soft">Nothing has been reported against {assetTag} before.</p>
      ) : (
        <div aria-busy={reports.isFetching}>
          <ul className="flex flex-col gap-md" aria-label={`Damage reports on ${assetTag}`}>
            {data.items.map((report) => (
              <li key={report.id}>
                <ReportEntry report={report} ownerSignedIn={ownerSignedIn} onWritten={setMoved} />
              </li>
            ))}
          </ul>
          {data.total > data.items.length && (
            <p className="mt-md text-sm text-slate-soft">
              Showing the {countOf(data.items.length, 'newest report', 'newest reports')} of {data.total}.
            </p>
          )}
        </div>
      )}
    </Card>
  )
}
