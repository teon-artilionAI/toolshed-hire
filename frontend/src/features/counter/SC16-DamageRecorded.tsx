/**
 * What SC-16 shows once a damage report is filed, from the report the server
 * answered with.
 *
 * It gives the reference of the report and repeats what was saved, because
 * the next thing that happens is a customer asking what has just been written
 * down about them. When the report belongs to a hire, the first way on is back
 * to the return of that hire, where the assistant sees the deposit settled.
 * The return reads the hire afresh, because filing the report dropped it from
 * the cache.
 */

import type { RefObject } from 'react'
import { Link } from 'react-router-dom'
import type { AssetStatus, DamageReport } from '../../shared/api/contract'
import { money } from '../../shared/format'
import { branchDateTime } from '../../shared/today'
import { Card, Notice, StatusPill } from '../../shared/ui'
import { ASSET_STATUS_LABEL, DAMAGE_SEVERITY_LABEL } from './counter-labels'
import { COUNTER_HOME_PATH, rentalHref } from './counter-links'
import { statusAfterFiling } from './SC16-damage-model'

/** Who pays, in words, from what the server recorded. */
function whoPays(report: DamageReport): string {
  if (!report.chargeableToCustomer) return 'Nobody. Toolshed Hire absorbs the repair.'
  if (report.recoveryCharged === null) return 'The customer. The report belongs to no hire, so no charge was raised.'
  return `The customer, ${money(report.recoveryCharged)} including VAT, withheld from the deposit of the hire.`
}

function Saved({ label, children }: { label: string; children: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm text-slate-soft">{label}</dt>
      <dd className="break-words text-sm text-ink">{children}</dd>
    </div>
  )
}

export function DamageRecorded({
  report,
  unitStatus,
  noticeRef,
  locatorHref,
}: {
  report: DamageReport
  /** The state of the unit as the screen last read it, before or after filing. */
  unitStatus: AssetStatus
  /** Where focus goes once the report is filed. */
  noticeRef: RefObject<HTMLDivElement | null>
  locatorHref: string
}) {
  const unitNow = statusAfterFiling(unitStatus)
  return (
    <div className="flex flex-col gap-md">
      <div ref={noticeRef} tabIndex={-1}>
        <Notice tone="success" title={`Damage report ${report.reference} is filed`}>
          <p>
            {report.assetTag} is {unitNow === 'UNDER_REPAIR' ? 'in the workshop' : 'in quarantine'} and cannot be
            booked until the owner resolves the report.
            {report.rentalReference === null
              ? ''
              : ` Go back to the return of ${report.rentalReference} to see where its deposit stands.`}
          </p>
        </Notice>
      </div>
      <Card title="What was saved">
        <dl className="grid gap-md sm:grid-cols-2">
          <Saved label="Reference">{report.reference}</Saved>
          <Saved label="Unit">{`${report.assetTag}, ${report.modelName}`}</Saved>
          <Saved label="Severity">{DAMAGE_SEVERITY_LABEL[report.severity]}</Saved>
          <Saved label="Estimated repair">{money(report.repairEstimate)}</Saved>
          <Saved label="Who pays">{whoPays(report)}</Saved>
          <Saved label="Replacement value">{money(report.replacementValue)}</Saved>
          <Saved label="Filed">{`${branchDateTime(report.reportedAt)} by ${report.reportedByName}`}</Saved>
          <div>
            <dt className="text-sm text-slate-soft">New state of the unit</dt>
            <dd>
              <StatusPill status={unitNow} label={ASSET_STATUS_LABEL[unitNow]} />
            </dd>
          </div>
        </dl>
        <div className="mt-lg flex flex-wrap gap-sm border-t border-line pt-md">
          {report.rentalId !== null && (
            <Link to={rentalHref(report.rentalId)} className="btn-primary px-md">
              Back to the return of {report.rentalReference ?? 'the hire'}
            </Link>
          )}
          <Link to={COUNTER_HOME_PATH} className={report.rentalId === null ? 'btn-primary px-md' : 'btn-secondary px-md'}>
            Back to today
          </Link>
          {report.rentalId === null && (
            <Link to={locatorHref} className="btn-secondary px-md">
              Open the asset locator
            </Link>
          )}
        </div>
      </Card>
    </div>
  )
}
