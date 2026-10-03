/**
 * One damage report on SC-16, as the counter and the owner read it.
 *
 * Every report says its reference, its status in words beside its colour, how
 * bad the damage was, who filed it and when, what is broken, the estimate and
 * whether the customer was charged. A closed report says when, what the repair
 * cost and the notes.
 *
 * An open report offers the owner's two moves to a signed in administrator and
 * to nobody else. "Send for repair" sends one request at once, because it only
 * moves the report and the unit to the workshop. "Resolve" opens the form in
 * SC16-Resolve-Form.tsx, which asks before it closes the report. Counter staff
 * see the status and a sentence that the owner resolves reports.
 */

import { useState } from 'react'
import { Wrench } from 'lucide-react'
import type { DamageReport } from '../../shared/api/contract'
import { OPEN_DAMAGE_STATUSES, sendForRepair } from '../../shared/api/damage-reports'
import { ErrorState } from '../../shared/async-states'
import { money } from '../../shared/format'
import { branchDateTime } from '../../shared/today'
import { Notice, StatusPill } from '../../shared/ui'
import { DAMAGE_SEVERITY_LABEL, DAMAGE_STATUS_LABEL, DAMAGE_STATUS_PILL } from './counter-labels'
import { ResolveForm } from './SC16-Resolve-Form'
import { useDamageWrite } from './use-damage-write'

/** Said to counter staff under an open report. */
export const OWNER_RESOLVES =
  'The owner resolves damage reports. Ask them when the unit should go back on the shelf.'

/** Whether the customer was charged, in words. */
function chargedInWords(report: DamageReport): string {
  if (!report.chargeableToCustomer) return 'The customer was not charged.'
  if (report.recoveryCharged === null) return 'Marked as chargeable. It belongs to no hire, so no charge was raised.'
  return `The customer was charged ${money(report.recoveryCharged)}, including VAT.`
}

/** How a closed report was closed, in words. */
function closedInWords(report: DamageReport): string {
  const when = report.resolvedAt === null ? '' : ` ${branchDateTime(report.resolvedAt)}`
  const cost = report.actualRepairCost === null ? '' : ` The repair cost ${money(report.actualRepairCost)}.`
  return `${report.status === 'WRITTEN_OFF' ? 'Written off' : 'Resolved'}${when}.${cost}`
}

/** The owner's two moves on one open report. */
function OwnerActions({
  report,
  onWritten,
}: {
  report: DamageReport
  onWritten: (report: DamageReport) => void
}) {
  const repair = useDamageWrite(report.reference, 'repair')
  const [resolving, setResolving] = useState(false)
  const failure = repair.failure

  if (resolving) {
    return <ResolveForm report={report} onResolved={onWritten} onCancel={() => setResolving(false)} />
  }
  return (
    <div className="mt-md border-t border-line pt-md">
      <div className="flex flex-wrap gap-sm">
        {report.status === 'OPEN' && (
          <button
            type="button"
            className="btn-secondary px-md"
            disabled={repair.pending}
            onClick={() => repair.send(() => sendForRepair(report.id), onWritten)}
          >
            <Wrench className="h-4 w-4 shrink-0" aria-hidden="true" />
            {repair.pending ? 'Sending for repair' : 'Send for repair'}{' '}
            <span className="sr-only">{report.reference}</span>
          </button>
        )}
        <button type="button" className="btn-primary px-md" disabled={repair.pending} onClick={() => setResolving(true)}>
          Resolve <span className="sr-only">{report.reference}</span>
        </button>
      </div>
      <p className="field-help">
        {report.status === 'OPEN' ? 'Send for repair moves the report and the unit to the workshop. ' : ''}
        Resolve closes the report as repaired or written off.
      </p>
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-sm">
          <ErrorState heading="We could not send the report for repair" error={failure.error} />
        </div>
      )}
      {failure !== null && failure.kind !== 'fault' && (
        <div className="mt-sm">
          <Notice tone="error" title="The report was not sent for repair">
            <p>{failure.detail}</p>
          </Notice>
        </div>
      )}
    </div>
  )
}

export function ReportEntry({
  report,
  ownerSignedIn,
  onWritten,
}: {
  report: DamageReport
  /** True only for a signed in administrator. */
  ownerSignedIn: boolean
  /** Called with the report the server answered a move with. */
  onWritten: (report: DamageReport) => void
}) {
  const open = OPEN_DAMAGE_STATUSES.includes(report.status)
  const titleId = `damage-report-${report.id}`
  return (
    <article aria-labelledby={titleId} className="min-w-0 rounded-lg border border-line bg-surface p-md">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <h3 id={titleId} className="font-mono text-sm font-semibold text-ink">
          {report.reference}
        </h3>
        <StatusPill status={DAMAGE_STATUS_PILL[report.status]} label={DAMAGE_STATUS_LABEL[report.status]} />
      </div>
      <p className="mt-xs break-words text-sm text-slate-soft">
        {DAMAGE_SEVERITY_LABEL[report.severity]}. Reported {branchDateTime(report.reportedAt)} by {report.reportedByName}
        {report.rentalReference === null ? '' : `, from hire ${report.rentalReference}`}.
      </p>
      <p className="mt-xs break-words text-sm text-ink">{report.description}</p>
      <p className="tabular mt-xs text-sm text-slate-soft">
        Repair estimated at {money(report.repairEstimate)}. {chargedInWords(report)}
      </p>
      {!open && (
        <p className="tabular mt-xs break-words text-sm text-slate-soft">
          {closedInWords(report)}
          {report.resolutionNotes === null ? '' : ` ${report.resolutionNotes}`}
        </p>
      )}
      {open && ownerSignedIn && <OwnerActions report={report} onWritten={onWritten} />}
      {open && !ownerSignedIn && <p className="mt-sm text-sm text-ink">{OWNER_RESOLVES}</p>}
    </article>
  )
}
