/**
 * The confirmation shown once an SC-16 damage report has been recorded.
 *
 * It repeats every value that was saved, because the next thing that
 * happens is a customer asking what has just been written down about them.
 */

import { Link } from 'react-router-dom'
import { humanise, money } from '../../shared/format'
import { Card, Notice, PageHeader, StatusPill } from '../../shared/ui'
import type { Severity } from './SC16-DamageFields'

export function DamageRecorded({
  tag,
  modelName,
  severity,
  estimate,
  chargeable,
  photographs,
  assetId,
}: {
  tag: string
  modelName: string
  severity: Severity
  estimate: number
  chargeable: boolean
  photographs: number
  assetId: string
}) {
  return (
    <>
      <PageHeader
        screenId="SC-16"
        title="Record damage"
        subtitle={`${tag} is off hire and in quarantine.`}
      />
      <Notice tone="success" title="Damage recorded">
        {tag} has moved to quarantine and will not show as available stock until
        the workshop signs it off.
      </Notice>
      <Card title="What was saved" className="mt-md">
        <dl className="grid gap-md sm:grid-cols-2">
          <div>
            <dt className="text-sm text-slate-soft">Unit</dt>
            <dd className="font-mono text-sm text-ink">
              {tag}, {modelName}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-slate-soft">Severity</dt>
            <dd className="text-sm text-ink">{humanise(severity)}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-soft">Estimated repair</dt>
            <dd className="tabular text-sm text-ink">{money(estimate)}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-soft">Who pays</dt>
            <dd className="text-sm text-ink">
              {chargeable
                ? 'Charged to the customer, taken off the deposit at settlement'
                : 'Absorbed by Toolshed Hire as fair wear and tear'}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-slate-soft">Photographs attached</dt>
            <dd className="tabular text-sm text-ink">{photographs}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-soft">New asset state</dt>
            <dd>
              <StatusPill status="QUARANTINED" />
            </dd>
          </div>
        </dl>
        <div className="mt-lg flex flex-wrap gap-sm border-t border-line pt-md">
          <Link to="/counter" className="btn-primary px-md">
            Back to today
          </Link>
          <Link to={`/counter/damage/${assetId}`} className="btn-secondary px-md">
            Record another fault on this unit
          </Link>
        </div>
      </Card>
    </>
  )
}
