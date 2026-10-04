/**
 * One page of the register on SC-21, as a table.
 *
 * Each unit shows its tag and serial number, its model and category, its
 * branch, where it stands in words beside its colour with the day it was
 * retired, its grade, and its open damage reports, each count a link to the
 * damage screen of the unit where they are dealt with. Every value is the
 * server's, in the order the server sent the units. Nothing is counted or
 * worked out.
 *
 * Seven columns do not fit across a phone, so below the `lg` width each unit
 * is drawn as a block with every value on a line of its own and the name of
 * its column beside it. It is the same table either way, and each part states
 * its role, because changing how a table is displayed can make a browser stop
 * reporting it as one.
 */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { FolderOpen, Wrench } from 'lucide-react'
import type { AdminAsset } from '../../shared/api/contract'
import { formatDate } from '../../shared/format'
import { StatusPill } from '../../shared/ui'
import { ASSET_STATUS_LABEL, CONDITION_GRADE_LABEL, countOf } from '../counter/counter-labels'
import { damageHref } from '../counter/counter-links'
import { openUnitLinkId } from './asset-address'

const COLUMNS = ['Unit', 'Model', 'Branch', 'Status', 'Condition', 'Open damage reports', 'Actions'] as const

/** What every cell shares. A table cell from `lg` up, and a line of a block below it. */
const CELL_BASE = 'td px-0 py-xs text-left lg:table-cell lg:px-md lg:py-sm'

/** A cell that shows the name of its column beside its value below `lg`. A
 *  value too wide to sit beside the name, such as the longest status, goes to
 *  the line below it instead of past the edge. */
const LABELLED_CELL = `${CELL_BASE} flex flex-wrap items-baseline justify-between gap-x-md`

function Labelled({ column, children }: { column: string; children: ReactNode }) {
  return (
    <td role="cell" className={LABELLED_CELL}>
      <span className="shrink-0 text-sm text-slate-soft lg:hidden">{column}</span>
      <span className="ml-auto min-w-0 text-right text-ink lg:ml-0 lg:text-left">{children}</span>
    </td>
  )
}

function DamageReports({ unit }: { unit: AdminAsset }) {
  if (unit.openDamageReports === 0) return <span className="text-slate-soft">None</span>
  return (
    <Link to={damageHref(unit.assetTag)} className="inline-flex min-h-[2.75rem] items-center gap-xs underline">
      <Wrench className="h-4 w-4 shrink-0" aria-hidden="true" />
      {countOf(unit.openDamageReports, 'open report', 'open reports')}{' '}
      <span className="sr-only">on {unit.assetTag}</span>
    </Link>
  )
}

function UnitRow({ unit, href }: { unit: AdminAsset; href: string }) {
  return (
    <tr role="row" className="block px-md py-sm lg:table-row">
      <th role="rowheader" scope="row" className={`${CELL_BASE} block font-medium text-ink`}>
        <span className="block break-all font-mono">{unit.assetTag}</span>
        {unit.serialNumber !== null && (
          <span className="mt-xs block break-all text-xs font-normal text-slate-soft">Serial {unit.serialNumber}</span>
        )}
      </th>
      <Labelled column="Model">
        <span className="block break-words">{unit.modelName}</span>
        <span className="block break-words text-xs text-slate-soft">{unit.categoryName}</span>
      </Labelled>
      <Labelled column="Branch">
        <span className="break-words">{unit.branchName}</span>
      </Labelled>
      <Labelled column="Status">
        <StatusPill status={unit.status} label={ASSET_STATUS_LABEL[unit.status]} />
        {unit.retiredOn !== null && (
          <span className="mt-xs block text-xs text-slate-soft">Since {formatDate(unit.retiredOn)}</span>
        )}
      </Labelled>
      <Labelled column="Condition">{CONDITION_GRADE_LABEL[unit.conditionGrade]}</Labelled>
      <Labelled column="Open damage reports">
        <DamageReports unit={unit} />
      </Labelled>
      <td role="cell" className={`${CELL_BASE} block pt-sm`}>
        <Link id={openUnitLinkId(unit.assetTag)} to={href} className="btn-secondary px-md">
          <FolderOpen className="h-4 w-4 shrink-0" aria-hidden="true" />
          Open <span className="sr-only">{unit.assetTag}</span>
        </Link>
      </td>
    </tr>
  )
}

export default function AssetTable({
  units,
  hrefOf,
}: {
  units: readonly AdminAsset[]
  /** The address of the register with one unit open, by its tag. */
  hrefOf: (tag: string) => string
}) {
  return (
    <div className="table-wrap">
      <table role="table" className="block w-full border-collapse lg:table">
        <caption className="sr-only">
          Each unit with its model, its branch, where it stands, its condition and its open damage reports.
        </caption>
        <thead role="rowgroup" className="hidden border-b border-line bg-muted lg:table-header-group">
          <tr role="row">
            {COLUMNS.map((heading) => (
              <th key={heading} role="columnheader" scope="col" className="th whitespace-normal">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup" className="block divide-y divide-line lg:table-row-group">
          {units.map((unit) => (
            <UnitRow key={unit.id} unit={unit} href={hrefOf(unit.assetTag)} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
