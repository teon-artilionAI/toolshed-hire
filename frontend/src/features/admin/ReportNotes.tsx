/**
 * What the SC-22 figures mean, in the server's own words.
 *
 * The two definitions come with every answer of the report route, and they
 * are shown here in full and as they arrived, in the same place as the
 * figures. A limit written down somewhere else is a limit nobody reads, and a
 * definition kept in the browser could drift from the sum the server does.
 */

import { Info } from 'lucide-react'
import type { ReportDefinitions } from '../../shared/api/contract'
import { GROSS_CONTRIBUTION } from './report-labels'

export default function ReportNotes({ definitions }: { definitions: ReportDefinitions }) {
  return (
    <section aria-labelledby="report-definitions-heading" className="card mb-lg p-lg">
      <h2
        id="report-definitions-heading"
        className="mb-md flex items-center gap-sm text-sm font-semibold uppercase tracking-wide text-slate-soft"
      >
        <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
        What these figures mean
      </h2>
      <dl className="grid gap-md text-sm lg:grid-cols-2">
        <div>
          <dt className="font-semibold text-ink">Utilisation</dt>
          <dd className="mt-xs break-words text-slate">{definitions.utilisation}</dd>
        </div>
        <div>
          <dt className="font-semibold text-ink">{GROSS_CONTRIBUTION}</dt>
          <dd className="mt-xs break-words text-slate">{definitions.grossContribution}</dd>
        </div>
      </dl>
    </section>
  )
}
