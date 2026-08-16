/**
 * Working out what is overdue and what it has cost, for SC-18.
 *
 * The fee is deliberately kept as its two parts, the daily rate and the days
 * late, rather than only as a total. A counter assistant reads both down the
 * phone, and a figure nobody can explain is a figure nobody collects.
 */

import { assets, branches, customers, productModels, rentals } from '../../shared/fixtures'
import type { BranchCode } from '../../shared/types'
import { daysOverdue, isOverdue } from '../../shared/format'

/** A hire goes to the owner for formal recovery at this point. */
export const ESCALATION_DAYS = 14

export type AgeFilter = 'ALL' | 'FRESH' | 'CHASING' | 'ESCALATED'

/** The oldest bucket a hire can sit in before escalation. */
const CHASING_FROM_DAYS = 4

export interface OverdueUnit {
  tag: string
  perDay: number
}

export interface OverdueRow {
  rentalId: string
  reference: string
  customerName: string
  customerPhone: string
  branchCode: BranchCode
  branchName: string
  dueBackOn: string
  daysLate: number
  units: OverdueUnit[]
  feePerDay: number
  feeToDate: number
  daysToEscalation: number
}

export const OVERDUE_ROWS: OverdueRow[] = rentals
  .filter(
    (rental) =>
      rental.status !== 'SETTLED' &&
      isOverdue(rental.dueBackOn) &&
      rental.items.some((item) => !item.returnedAt),
  )
  .map((rental) => {
    const customer = customers.find((c) => c.id === rental.customerId)
    const daysLate = daysOverdue(rental.dueBackOn)
    const units: OverdueUnit[] = rental.items
      .filter((item) => !item.returnedAt)
      .map((item) => {
        const asset = assets.find((a) => a.id === item.assetId)
        const model = productModels.find((m) => m.id === asset?.productModelId)
        return { tag: asset?.tag ?? 'Tag missing', perDay: model?.lateFeePerDay ?? 0 }
      })
    const feePerDay = units.reduce((sum, unit) => sum + unit.perDay, 0)
    return {
      rentalId: rental.id,
      reference: rental.reference,
      customerName: customer?.name ?? 'Unknown customer',
      customerPhone: customer?.phone ?? 'No number on file',
      branchCode: rental.branchCode,
      branchName:
        branches.find((b) => b.code === rental.branchCode)?.name ?? rental.branchCode,
      dueBackOn: rental.dueBackOn,
      daysLate,
      units,
      feePerDay,
      feeToDate: feePerDay * daysLate,
      daysToEscalation: ESCALATION_DAYS - daysLate,
    }
  })
  .sort((a, b) => b.daysLate - a.daysLate)

export function matchesAge(row: OverdueRow, filter: AgeFilter): boolean {
  if (filter === 'ALL') return true
  if (filter === 'FRESH') return row.daysLate < CHASING_FROM_DAYS
  if (filter === 'CHASING') return row.daysLate >= CHASING_FROM_DAYS && row.daysLate < ESCALATION_DAYS
  return row.daysLate >= ESCALATION_DAYS
}
