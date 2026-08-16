/**
 * SC-21 Asset Register and Lifecycle.
 *
 * Every physical unit the business owns, with the filters needed to find
 * one and the actions needed to move it through its life: added, amended,
 * quarantined, repaired, retired, written off.
 *
 * The rules live in admin-lifecycle.ts and the panels in their own files,
 * so this screen is the list and the wiring.
 */

import { useMemo, useState } from 'react'
import { AlertTriangle, Pencil, Plus, Repeat, Wrench } from 'lucide-react'
import type { Asset, AssetStatus, DamageReport } from '../../shared/types'
import {
  assets as seedAssets, branches, damageReports as seedReports, productModels,
} from '../../shared/fixtures'
import {
  Card, DataTable, EmptyState, Notice, PageHeader, StatTile, StatusPill,
} from '../../shared/ui'
import { formatDate, humanise, money } from '../../shared/format'
import { OFF_ROAD, OUT_OF_FLEET } from './admin-fleet'
import AssetForm from './SC21-Asset-Form'
import { DamageResolutionPanel, StatusChangePanel } from './SC21-Asset-Actions'
import type { DamageOutcome } from './SC21-Asset-Actions'
import AssetFilters from './SC21-Asset-Filters'
import { NO_FILTERS, matchesFilters } from './admin-asset-filters'

type Panel =
  | { kind: 'create' }
  | { kind: 'edit'; assetId: string }
  | { kind: 'status'; assetId: string }
  | { kind: 'damage'; assetId: string }
  | null

function modelFor(productModelId: string) {
  return productModels.find((m) => m.id === productModelId)
}

export default function AssetRegister() {
  const [fleet, setFleet] = useState<Asset[]>(seedAssets)
  const [reports, setReports] = useState<DamageReport[]>(seedReports)
  const [filters, setFilters] = useState(NO_FILTERS)
  const [panel, setPanel] = useState<Panel>(null)
  const [message, setMessage] = useState('')

  const openReportFor = (assetId: string) =>
    reports.find((r) => r.assetId === assetId && r.status !== 'RESOLVED')

  const shown = useMemo(
    () => fleet.filter((asset) => matchesFilters(asset, modelFor(asset.productModelId), filters)),
    [fleet, filters],
  )

  const active = panel && 'assetId' in panel ? fleet.find((a) => a.id === panel.assetId) : undefined

  const saveAsset = (saved: Asset) => {
    setFleet((list) =>
      list.some((a) => a.id === saved.id)
        ? list.map((a) => (a.id === saved.id ? saved : a))
        : [...list, saved],
    )
    setMessage(
      panel?.kind === 'create'
        ? `${saved.tag} has been added to the ${branches.find((b) => b.code === saved.branchCode)?.name} fleet.`
        : `${saved.tag} has been updated.`,
    )
    setPanel(null)
  }

  const applyStatus = (asset: Asset, to: AssetStatus, reason: string) => {
    setFleet((list) => list.map((a) => (a.id === asset.id ? { ...a, status: to } : a)))
    setMessage(
      `${asset.tag} is now ${humanise(to).toLowerCase()}.${reason ? ` Reason recorded: ${reason}` : ''}`,
    )
    setPanel(null)
  }

  const resolveDamage = (
    report: DamageReport, asset: Asset, actualRepairCost: number, outcome: DamageOutcome,
  ) => {
    setReports((list) =>
      list.map((r) => (r.id === report.id ? { ...r, status: 'RESOLVED', actualRepairCost } : r)),
    )
    const next: AssetStatus = outcome === 'REPAIRED' ? 'AVAILABLE' : 'RETIRED'
    setFleet((list) => list.map((a) => (a.id === asset.id ? { ...a, status: next } : a)))
    setMessage(
      outcome === 'REPAIRED'
        ? `${asset.tag} is repaired at a cost of ${money(actualRepairCost)} and is back on the shelf.`
        : `${asset.tag} has been written off. ${money(actualRepairCost)} was spent before the decision.`,
    )
    setPanel(null)
  }

  const inFleet = fleet.filter((a) => !OUT_OF_FLEET.includes(a.status))
  const openReports = reports.filter((r) => r.status !== 'RESOLVED')

  return (
    <>
      <PageHeader
        screenId="SC-21"
        title="Asset register"
        subtitle="Every unit the business owns, where it is and what state it is in. A unit only moves to a status its lifecycle allows."
        actions={
          <button type="button" className="btn-primary px-md" onClick={() => setPanel({ kind: 'create' })}>
            <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
            Add a unit
          </button>
        }
      />

      {/* Notice already carries role="status", so it announces itself once. */}
      {message && (
        <div className="mb-lg">
          <Notice tone="success" title={message} />
        </div>
      )}

      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Units in the fleet" value={inFleet.length} hint={`${fleet.length} on the register in total`} />
        <StatTile
          label="Out on hire"
          value={fleet.filter((a) => a.status === 'ON_HIRE').length}
          hint="With customers right now"
          tone="good"
        />
        <StatTile
          label="Off the road"
          value={fleet.filter((a) => OFF_ROAD.includes(a.status)).length}
          hint="Quarantined or in for repair"
          tone={fleet.some((a) => OFF_ROAD.includes(a.status)) ? 'warn' : 'good'}
        />
        <StatTile
          label="Damage reports open"
          value={openReports.length}
          hint="Waiting on a repair cost and a decision"
          tone={openReports.length > 0 ? 'bad' : 'good'}
        />
      </div>

      {panel?.kind === 'create' && (
        <div className="mb-lg">
          <Card title="Add a unit to the fleet">
            <AssetForm
              models={productModels}
              takenTags={fleet.map((a) => a.tag.toUpperCase())}
              onSave={saveAsset}
              onCancel={() => setPanel(null)}
            />
          </Card>
        </div>
      )}

      {panel?.kind === 'edit' && active && (
        <div className="mb-lg">
          <Card title={`Amend ${active.tag}`}>
            <AssetForm
              key={active.id}
              asset={active}
              models={productModels}
              takenTags={fleet.filter((a) => a.id !== active.id).map((a) => a.tag.toUpperCase())}
              onSave={saveAsset}
              onCancel={() => setPanel(null)}
            />
          </Card>
        </div>
      )}

      {panel?.kind === 'status' && active && (
        <div className="mb-lg">
          <Card title={`Change the status of ${active.tag}`}>
            <StatusChangePanel
              key={active.id}
              asset={active}
              model={modelFor(active.productModelId)}
              hasOpenDamage={openReportFor(active.id) !== undefined}
              onApply={(to, reason) => applyStatus(active, to, reason)}
              onCancel={() => setPanel(null)}
            />
          </Card>
        </div>
      )}

      {panel?.kind === 'damage' && active && openReportFor(active.id) && (
        <div className="mb-lg">
          <Card title={`Resolve the damage report on ${active.tag}`}>
            <DamageResolutionPanel
              key={active.id}
              report={openReportFor(active.id) as DamageReport}
              asset={active}
              model={modelFor(active.productModelId)}
              onResolve={(cost, outcome) =>
                resolveDamage(openReportFor(active.id) as DamageReport, active, cost, outcome)
              }
              onCancel={() => setPanel(null)}
            />
          </Card>
        </div>
      )}

      <Card title={`Units on the register (${shown.length})`}>
        <AssetFilters value={filters} onChange={setFilters} />

        {shown.length === 0 ? (
          <EmptyState
            title="No units match what you asked for"
            body="Nothing on the register matches that search and those filters together. Widen the search or clear the filters and start again."
            action={
              <button
                type="button"
                className="btn-secondary px-md"
                onClick={() => setFilters(NO_FILTERS)}
              >
                Clear the filters
              </button>
            }
          />
        ) : (
          <DataTable
            caption="Every unit on the register, with its branch, status, condition and purchase details."
            columns={['Tag', 'Tool', 'Branch', 'Status', 'Condition', 'Meter hours', 'Bought', 'Purchase price', 'Actions']}
          >
            {shown.map((asset) => {
              const model = modelFor(asset.productModelId)
              const report = openReportFor(asset.id)
              return (
                <tr key={asset.id}>
                  <td className="td font-mono font-medium text-ink">{asset.tag}</td>
                  <td className="td">
                    <p className="text-ink">{model?.name ?? 'Unknown tool'}</p>
                    <p className="text-xs text-slate-soft">{model?.manufacturer}</p>
                  </td>
                  <td className="td text-slate-soft">{asset.branchCode}</td>
                  <td className="td">
                    <StatusPill status={asset.status} />
                    {report && (
                      <p className="mt-xs flex items-center gap-xs text-xs text-status-due">
                        <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
                        Damage report open
                      </p>
                    )}
                  </td>
                  <td className="td tabular">{asset.condition}</td>
                  <td className="td tabular">{asset.meterHours ?? 'No meter'}</td>
                  <td className="td whitespace-nowrap text-slate-soft">{formatDate(asset.acquiredOn)}</td>
                  <td className="td tabular">{money(asset.acquisitionCost)}</td>
                  <td className="td">
                    <div className="flex flex-wrap gap-sm">
                      <button
                        type="button"
                        className="btn-secondary px-md text-sm"
                        onClick={() => setPanel({ kind: 'edit', assetId: asset.id })}
                      >
                        <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
                        Amend
                        <span className="sr-only"> {asset.tag}</span>
                      </button>
                      <button
                        type="button"
                        className="btn-secondary px-md text-sm"
                        onClick={() => setPanel({ kind: 'status', assetId: asset.id })}
                      >
                        <Repeat className="h-4 w-4 shrink-0" aria-hidden="true" />
                        Status
                        <span className="sr-only"> of {asset.tag}</span>
                      </button>
                      {report && (
                        <button
                          type="button"
                          className="btn-primary px-md text-sm"
                          onClick={() => setPanel({ kind: 'damage', assetId: asset.id })}
                        >
                          <Wrench className="h-4 w-4 shrink-0" aria-hidden="true" />
                          Resolve damage
                          <span className="sr-only"> on {asset.tag}</span>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </DataTable>
        )}
      </Card>
    </>
  )
}
