/**
 * The two cards under the SC-22 table.
 *
 * The first names the units that earned nothing, because "which of my tools
 * are dead weight" is the question the client actually asked. The second
 * states what the figures do and do not include, in the same place as the
 * figures, because a limit written down somewhere else is a limit nobody
 * reads.
 */

import { Info } from 'lucide-react'
import { Card, EmptyState, Notice, StatusPill } from '../../shared/ui'
import type { AssetMetric } from './report-metrics'

const METHOD_NOTES = [
  'Days run half open. Out on the 6th, back on the 10th is four days, and the unit is free again on the 10th.',
  'A hire collected today and not yet returned counts as one day, because a started day is a charged day.',
  'Days past the due date are charged at the late fee rate, not the hire rate, so the two columns never double count.',
  'Repairs we recharge to the customer are left out of the cost column. Only repairs we absorb reduce contribution.',
  'Retired units are excluded. A retired unit is not idle, it is gone.',
  'This prototype runs on a sample of the fleet and a handful of hires, so the percentages read low. The calculation is the thing being shown, not the trading figures.',
]

export default function ReportNotes({
  idle,
  unitCount,
  periodLabel,
}: {
  idle: AssetMetric[]
  unitCount: number
  periodLabel: string
}) {
  return (
    <div className="grid gap-md lg:grid-cols-2">
      <Card title="Units that earned nothing this period">
        {idle.length === 0 ? (
          <EmptyState
            title="Every unit went out at least once"
            body="Nothing in this filter sat in the yard for the whole period."
          />
        ) : (
          <>
            <p className="mb-md text-sm text-slate-soft">
              {idle.length} of {unitCount} units did not leave the yard{' '}
              {periodLabel.toLowerCase()}. Quarantined and maintenance units are
              included, because a unit under repair still costs money to own.
            </p>
            <ul className="flex flex-wrap gap-sm">
              {idle.map((unit) => (
                <li
                  key={unit.assetId}
                  className="flex items-center gap-sm rounded border border-line bg-muted px-sm py-xs"
                >
                  <span className="font-mono text-xs text-ink">{unit.tag}</span>
                  <StatusPill status={unit.status} />
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card title="How these figures are worked out">
        <div className="space-y-md text-sm text-slate-soft">
          <Notice tone="info" title="Gross contribution, not profit">
            Hire income plus late fees, less the repair cost we carry ourselves.
            It carries no depreciation, no wages, no rent and no finance cost,
            because the system does not hold them. Treat it as a ranking of
            which units pull their weight, not as a bottom line.
          </Notice>
          <ul className="space-y-sm">
            {METHOD_NOTES.map((line) => (
              <li key={line} className="flex items-start gap-sm">
                <Info
                  className="mt-0.5 h-4 w-4 shrink-0 text-slate-faint"
                  aria-hidden="true"
                />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>
      </Card>
    </div>
  )
}
