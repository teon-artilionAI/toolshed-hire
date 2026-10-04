/**
 * The fields of one unit on SC-21, as the server holds them.
 *
 * Its model, branch, status in words beside its colour, grade, serial number,
 * the day it was bought and what it cost, its meter reading, its notes, the
 * bookings that hold it now and its open damage reports. The open reports
 * link to the damage screen of the unit, where the owner resolves them. Every
 * value is the server's, and nothing is worked out.
 */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Wrench } from 'lucide-react'
import type { AdminAssetDetail } from '../../shared/api/contract'
import { formatDate, money } from '../../shared/format'
import { StatusPill } from '../../shared/ui'
import { ASSET_STATUS_LABEL, CONDITION_GRADE_LABEL, countOf } from '../counter/counter-labels'
import { damageHref } from '../counter/counter-links'

function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-soft">{term}</dt>
      <dd className="mt-xs break-words text-sm text-ink">{children}</dd>
    </div>
  )
}

function OpenReports({ unit }: { unit: AdminAssetDetail }) {
  if (unit.openDamageReports === 0) return <>None</>
  return (
    <Link to={damageHref(unit.assetTag)} className="inline-flex min-h-[2.75rem] items-center gap-xs underline">
      <Wrench className="h-4 w-4 shrink-0" aria-hidden="true" />
      {countOf(unit.openDamageReports, 'open damage report', 'open damage reports')}, resolve on the damage screen
    </Link>
  )
}

export function AssetFacts({ unit }: { unit: AdminAssetDetail }) {
  return (
    <dl className="grid gap-md sm:grid-cols-2 lg:grid-cols-3">
      <Fact term="Model">
        {unit.modelName}
        <span className="block text-xs text-slate-soft">{unit.categoryName}</span>
      </Fact>
      <Fact term="Branch">{unit.branchName}</Fact>
      <Fact term="Status">
        <StatusPill status={unit.status} label={ASSET_STATUS_LABEL[unit.status]} />
        {unit.retiredOn !== null && <span className="mt-xs block">Retired on {formatDate(unit.retiredOn)}</span>}
      </Fact>
      <Fact term="Condition">{CONDITION_GRADE_LABEL[unit.conditionGrade]}</Fact>
      <Fact term="Serial number">
        {unit.serialNumber === null ? 'None recorded' : <span className="break-all font-mono">{unit.serialNumber}</span>}
      </Fact>
      <Fact term="Bought">
        {formatDate(unit.acquiredOn)} for <span className="tabular">{money(unit.acquisitionCost)}</span>
      </Fact>
      <Fact term="Meter reading">
        {unit.hourMeterReading === null ? 'No meter' : countOf(unit.hourMeterReading, 'hour', 'hours')}
      </Fact>
      <Fact term="Bookings holding it now">
        {unit.activeAllocationCount === 0 ? 'None' : countOf(unit.activeAllocationCount, 'booking', 'bookings')}
      </Fact>
      <Fact term="Open damage reports">
        <OpenReports unit={unit} />
      </Fact>
      <div className="min-w-0 sm:col-span-2 lg:col-span-3">
        <dt className="text-xs font-semibold uppercase tracking-wide text-slate-soft">Notes</dt>
        <dd className="mt-xs whitespace-pre-line break-words text-sm text-ink">{unit.notes ?? 'None'}</dd>
      </div>
    </dl>
  )
}
