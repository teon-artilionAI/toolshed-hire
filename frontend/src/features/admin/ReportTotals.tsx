/**
 * The totals at the top of the SC-22 report.
 *
 * They are the server's totals over every row of the report, every page and
 * not only the one on the screen. The browser adds none of them up. The
 * figure is called gross contribution, and the sentence under it says what it
 * leaves out, so it is never read as profit.
 */

import type { ReportFigures } from '../../shared/api/contract'
import { isNegativeMoney, money } from '../../shared/format'
import { StatTile } from '../../shared/ui'
import { countOf } from '../counter/counter-labels'
import { GROSS_CONTRIBUTION, utilisationWords } from './report-labels'

export default function ReportTotals({ totals }: { totals: ReportFigures }) {
  const belowZero = isNegativeMoney(totals.grossContribution)
  return (
    <section aria-labelledby="report-totals-heading" className="mb-lg">
      <h2 id="report-totals-heading" className="mb-md text-sm font-semibold uppercase tracking-wide text-slate-soft">
        Totals for the whole report
      </h2>
      {/* Three across at most, so an amount in the millions stays on one line. */}
      <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-3">
        <StatTile
          label={GROSS_CONTRIBUTION}
          value={money(totals.grossContribution)}
          tone={belowZero ? 'bad' : 'default'}
          hint={
            belowZero
              ? 'Below zero. The repairs cost more than the fleet brought in. This is not profit.'
              : 'Revenue and recoveries less repair costs, excluding VAT. This is not profit.'
          }
        />
        <StatTile
          label="Utilisation"
          value={utilisationWords(totals.utilisationPercent)}
          hint={`${countOf(totals.daysOnHire, 'day', 'days')} on hire of ${countOf(totals.serviceableDays, 'serviceable day', 'serviceable days')}`}
        />
        <StatTile label="Hire revenue, excluding VAT" value={money(totals.hireRevenueExVat)} />
        <StatTile label="Late fees, excluding VAT" value={money(totals.lateFeesExVat)} />
        <StatTile label="Damage recovery, excluding VAT" value={money(totals.damageRecoveryExVat)} />
        <StatTile label="Repair costs" value={money(totals.repairCosts)} hint="Recorded against the units" />
        <StatTile
          label="Units counted"
          value={totals.assetCount}
          hint="In the fleet for some or all of the period"
        />
      </div>
    </section>
  )
}
