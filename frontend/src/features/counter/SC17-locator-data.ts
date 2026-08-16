/**
 * Working out where every unit on the fleet actually is, for SC-17.
 *
 * The join is done once at module load rather than per keystroke, because the
 * locator is used while somebody is holding on the phone and the search has
 * to feel instant.
 *
 * "Where it is" is deliberately a sentence rather than a status code. A unit
 * that is out is with a named person on a named hire, due back on a date, and
 * that is what gets read down the phone.
 */

import {
  assets,
  branches,
  categories,
  customers,
  damageReports,
  productModels,
  rentals,
  reservations,
} from '../../shared/fixtures'
import type { AssetStatus, BranchCode } from '../../shared/types'
import { formatDate, isOverdue } from '../../shared/format'

export interface LocatedAsset {
  id: string
  tag: string
  modelLabel: string
  categoryName: string
  sku: string
  branchCode: BranchCode
  branchName: string
  status: AssetStatus
  condition: string
  meterHours?: number
  /** One sentence a counter assistant can read straight out. */
  whereabouts: string
  late: boolean
}

function whereaboutsOf(assetId: string, status: AssetStatus, branchName: string) {
  const openHire = rentals.find((rental) =>
    rental.items.some((item) => item.assetId === assetId && !item.returnedAt),
  )
  if (openHire) {
    const who = customers.find((c) => c.id === openHire.customerId)?.name ?? 'a customer'
    return {
      text: `With ${who} on ${openHire.reference}, due back ${formatDate(openHire.dueBackOn)}`,
      late: isOverdue(openHire.dueBackOn),
    }
  }

  if (status === 'RESERVED') {
    const held = reservations.find(
      (reservation) =>
        reservation.lines.some((line) => line.allocatedAssetIds.includes(assetId)) &&
        (reservation.status === 'HELD' || reservation.status === 'CONFIRMED'),
    )
    if (held) {
      const who = customers.find((c) => c.id === held.customerId)?.name ?? 'a customer'
      return {
        text: `Held at ${branchName} for ${who}, collection ${formatDate(held.startDate)}`,
        late: false,
      }
    }
  }

  if (status === 'QUARANTINED' || status === 'MAINTENANCE') {
    const fault = damageReports.find(
      (report) => report.assetId === assetId && report.status !== 'RESOLVED',
    )
    return {
      text: fault
        ? `Workshop hold at ${branchName}, ${fault.severity.toLowerCase()} damage`
        : `Workshop hold at ${branchName}`,
      late: false,
    }
  }

  if (status === 'RETIRED') return { text: 'Retired, off the fleet', late: false }
  if (status === 'LOST') return { text: 'Reported lost, not on any shelf', late: false }
  return { text: `On the shelf at ${branchName}`, late: false }
}

export const LOCATED_ASSETS: LocatedAsset[] = assets.map((asset) => {
  const model = productModels.find((m) => m.id === asset.productModelId)
  const branchName =
    branches.find((b) => b.code === asset.branchCode)?.name ?? asset.branchCode
  const where = whereaboutsOf(asset.id, asset.status, branchName)
  return {
    id: asset.id,
    tag: asset.tag,
    modelLabel: model ? `${model.manufacturer} ${model.name}` : 'Unknown model',
    categoryName: categories.find((c) => c.id === model?.categoryId)?.name ?? '',
    sku: model?.sku ?? '',
    branchCode: asset.branchCode,
    branchName,
    status: asset.status,
    condition: asset.condition,
    meterHours: asset.meterHours,
    whereabouts: where.text,
    late: where.late,
  }
})
