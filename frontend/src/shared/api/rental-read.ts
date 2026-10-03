/**
 * The reader for a hire, as the checkout and the rental routes send it.
 *
 * A hire is the largest body the counter reads, so its reader has a file of
 * its own. It checks every member the contract names, the way every other
 * reader does, so a body that breaks the contract fails here with the name of
 * the field and not later on a screen.
 */

import { malformedResponse } from '../api-problem'
import type {
  ChargeStatus,
  ChargeType,
  ConditionGrade,
  DamageAssessment,
  Rental,
  RentalCharge,
  RentalItem,
  RentalStatus,
  SettlementWaitingOn,
} from './contract'
import {
  readCount,
  readDate,
  readFlag,
  readList,
  readMoney,
  readNullableCount,
  readNullableOneOf,
  readNullableText,
  readNullableTimestamp,
  readObject,
  readOneOf,
  readPercent,
  readSignedMoney,
  readText,
} from './read'

/** The grades a unit can be given, best first. */
export const CONDITION_GRADES: readonly ConditionGrade[] = ['A', 'B', 'C']

/** Every status a hire can be in. */
export const RENTAL_STATUSES: readonly RentalStatus[] = [
  'OPEN',
  'OVERDUE',
  'PARTIALLY_RETURNED',
  'RETURNED',
  'SETTLED',
]

const DAMAGE_ASSESSMENTS: readonly DamageAssessment[] = ['NOT_NEEDED', 'REQUIRED', 'DONE']

const SETTLEMENT_WAITS: readonly SettlementWaitingOn[] = [
  'ITEMS_OUT',
  'DAMAGE_ASSESSMENT',
  'BALANCE_PAYMENT',
]

const CHARGE_TYPES: readonly ChargeType[] = [
  'HIRE',
  'DEPOSIT_HOLD',
  'DEPOSIT_RELEASE',
  'DEPOSIT_FORFEIT',
  'LATE_FEE',
  'DAMAGE_RECOVERY',
  'CLEANING',
  'ADJUSTMENT',
]

const CHARGE_STATUSES: readonly ChargeStatus[] = ['PENDING', 'SETTLED', 'WAIVED', 'REVERSED']

/** An instant the contract never sends as null. */
function readTimestamp(record: Record<string, unknown>, key: string, path: string): string {
  const value = readNullableTimestamp(record, key, path)
  if (value === null) {
    throw malformedResponse(path, `Expected field ${key} from ${path} to be an instant, got null.`)
  }
  return value
}

function readRentalItem(value: unknown, path: string): RentalItem {
  const record = readObject(value, path, 'a rental item')
  return {
    id: readText(record, 'id', path),
    assetTag: readNullableText(record, 'assetTag', path),
    modelName: readText(record, 'modelName', path),
    modelSlug: readText(record, 'modelSlug', path),
    conditionOut: readOneOf(record, 'conditionOut', path, CONDITION_GRADES),
    conditionIn: readNullableOneOf(record, 'conditionIn', path, CONDITION_GRADES),
    hourMeterOut: readNullableCount(record, 'hourMeterOut', path),
    hourMeterIn: readNullableCount(record, 'hourMeterIn', path),
    accessoriesOut: readNullableText(record, 'accessoriesOut', path),
    accessoriesIn: readNullableText(record, 'accessoriesIn', path),
    returnedAt: readNullableTimestamp(record, 'returnedAt', path),
    daysLate: readCount(record, 'daysLate', path),
    lateFeePerDay: readMoney(record, 'lateFeePerDay', path),
    daysLateToday: readCount(record, 'daysLateToday', path),
    lateFeeToday: readMoney(record, 'lateFeeToday', path),
    damageAssessment: readOneOf(record, 'damageAssessment', path, DAMAGE_ASSESSMENTS),
  }
}

function readRentalCharge(value: unknown, path: string): RentalCharge {
  const record = readObject(value, path, 'a rental charge')
  return {
    id: readText(record, 'id', path),
    type: readOneOf(record, 'type', path, CHARGE_TYPES),
    description: readText(record, 'description', path),
    amountExVat: readSignedMoney(record, 'amountExVat', path),
    vatRate: readPercent(record, 'vatRate', path),
    vatAmount: readSignedMoney(record, 'vatAmount', path),
    amountIncVat: readSignedMoney(record, 'amountIncVat', path),
    status: readOneOf(record, 'status', path, CHARGE_STATUSES),
    raisedAt: readTimestamp(record, 'raisedAt', path),
    rentalItemId: readNullableText(record, 'rentalItemId', path),
  }
}

/** Read a hire, with every item and every charge on it. */
export function readRental(value: unknown, path: string): Rental {
  const record = readObject(value, path, 'a rental')
  return {
    id: readText(record, 'id', path),
    reference: readText(record, 'reference', path),
    status: readOneOf(record, 'status', path, RENTAL_STATUSES),
    reservationId: readText(record, 'reservationId', path),
    reservationReference: readText(record, 'reservationReference', path),
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    customerProfileId: readText(record, 'customerProfileId', path),
    customerName: readText(record, 'customerName', path),
    customerPhone: readText(record, 'customerPhone', path),
    from: readDate(record, 'from', path),
    dueBackOn: readDate(record, 'dueBackOn', path),
    checkedOutAt: readTimestamp(record, 'checkedOutAt', path),
    returnedAt: readNullableTimestamp(record, 'returnedAt', path),
    items: readList(record, 'items', path, readRentalItem),
    charges: readList(record, 'charges', path, readRentalCharge),
    depositHeld: readMoney(record, 'depositHeld', path),
    depositWithheld: readMoney(record, 'depositWithheld', path),
    depositRefunded: readMoney(record, 'depositRefunded', path),
    balanceDue: readMoney(record, 'balanceDue', path),
    settledAt: readNullableTimestamp(record, 'settledAt', path),
    agreementSigned: readFlag(record, 'agreementSigned', path),
    canReturn: readFlag(record, 'canReturn', path),
    settlementWaitingOn: readNullableOneOf(record, 'settlementWaitingOn', path, SETTLEMENT_WAITS),
  }
}
