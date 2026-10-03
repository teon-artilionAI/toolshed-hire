/**
 * The counter overview routes. What is due today at a branch, and its diary.
 *
 * Two reads, both for staff. Each runs the server's lazy sweep before it
 * answers, so a hold that has lapsed or a booking nobody came for is already
 * moved on by the time it is listed. Each function makes one call and reads
 * the body into its contract type, checking every member, so a body that
 * breaks the contract fails here with the name of the field.
 *
 * Every count, every day late and every late fee is the server's. Nothing here
 * or above it adds anything up.
 */

import { api } from './client'
import type {
  BranchDiary,
  CounterDashboard,
  DashboardCollection,
  DashboardCounts,
  DashboardOverdue,
  DashboardQuery,
  DashboardReturn,
  DiaryCollection,
  DiaryCollectionStatus,
  DiaryDay,
  DiaryQuery,
  DiaryReturn,
} from './contract'
import { readCount, readDate, readFlag, readList, readMoney, readObject, readOneOf, readText } from './read'
import { RENTAL_STATUSES } from './rental-read'

const DASHBOARD_ENDPOINT = '/counter/dashboard'
const DIARY_ENDPOINT = '/counter/diary'

/** The statuses a booking in the diary can be in, in the order it moves. */
const DIARY_COLLECTION_STATUSES: readonly DiaryCollectionStatus[] = [
  'CONFIRMED',
  'COLLECTED',
  'RETURNED',
  'NO_SHOW',
]

function readCounts(value: unknown, path: string): DashboardCounts {
  const record = readObject(value, path, 'the counts of a dashboard')
  return {
    collectionsDue: readCount(record, 'collectionsDue', path),
    returnsDue: readCount(record, 'returnsDue', path),
    overdue: readCount(record, 'overdue', path),
    onHire: readCount(record, 'onHire', path),
    quarantined: readCount(record, 'quarantined', path),
  }
}

function readDashboardCollection(value: unknown, path: string): DashboardCollection {
  const record = readObject(value, path, 'a collection due today')
  return {
    reservationId: readText(record, 'reservationId', path),
    reference: readText(record, 'reference', path),
    customerName: readText(record, 'customerName', path),
    customerPhone: readText(record, 'customerPhone', path),
    from: readDate(record, 'from', path),
    to: readDate(record, 'to', path),
    unitCount: readCount(record, 'unitCount', path),
    summary: readText(record, 'summary', path),
  }
}

function readDashboardReturn(value: unknown, path: string): DashboardReturn {
  const record = readObject(value, path, 'a return due today')
  return {
    rentalId: readText(record, 'rentalId', path),
    reference: readText(record, 'reference', path),
    customerName: readText(record, 'customerName', path),
    customerPhone: readText(record, 'customerPhone', path),
    dueBackOn: readDate(record, 'dueBackOn', path),
    itemsOut: readCount(record, 'itemsOut', path),
    itemCount: readCount(record, 'itemCount', path),
    summary: readText(record, 'summary', path),
  }
}

function readDashboardOverdue(value: unknown, path: string): DashboardOverdue {
  const record = readObject(value, path, 'an overdue hire')
  return {
    rentalId: readText(record, 'rentalId', path),
    reference: readText(record, 'reference', path),
    customerName: readText(record, 'customerName', path),
    customerPhone: readText(record, 'customerPhone', path),
    dueBackOn: readDate(record, 'dueBackOn', path),
    daysOverdue: readCount(record, 'daysOverdue', path),
    itemsOut: readCount(record, 'itemsOut', path),
    lateFeeAccrued: readMoney(record, 'lateFeeAccrued', path),
  }
}

function readDashboard(value: unknown, path: string): CounterDashboard {
  const record = readObject(value, path, 'a counter dashboard')
  return {
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    date: readDate(record, 'date', path),
    counts: readCounts(record.counts, path),
    collectionsDue: readList(record, 'collectionsDue', path, readDashboardCollection),
    returnsDue: readList(record, 'returnsDue', path, readDashboardReturn),
    overdue: readList(record, 'overdue', path, readDashboardOverdue),
  }
}

function readDiaryCollection(value: unknown, path: string): DiaryCollection {
  const record = readObject(value, path, 'a collection in the diary')
  return {
    reservationId: readText(record, 'reservationId', path),
    reference: readText(record, 'reference', path),
    status: readOneOf(record, 'status', path, DIARY_COLLECTION_STATUSES),
    customerName: readText(record, 'customerName', path),
    customerPhone: readText(record, 'customerPhone', path),
    from: readDate(record, 'from', path),
    to: readDate(record, 'to', path),
    unitCount: readCount(record, 'unitCount', path),
    summary: readText(record, 'summary', path),
    canMarkNoShow: readFlag(record, 'canMarkNoShow', path),
  }
}

function readDiaryReturn(value: unknown, path: string): DiaryReturn {
  const record = readObject(value, path, 'a return in the diary')
  return {
    rentalId: readText(record, 'rentalId', path),
    reference: readText(record, 'reference', path),
    status: readOneOf(record, 'status', path, RENTAL_STATUSES),
    customerName: readText(record, 'customerName', path),
    customerPhone: readText(record, 'customerPhone', path),
    dueBackOn: readDate(record, 'dueBackOn', path),
    itemsOut: readCount(record, 'itemsOut', path),
    itemCount: readCount(record, 'itemCount', path),
    summary: readText(record, 'summary', path),
  }
}

function readDiaryDay(value: unknown, path: string): DiaryDay {
  const record = readObject(value, path, 'a day of the diary')
  return {
    date: readDate(record, 'date', path),
    collections: readList(record, 'collections', path, readDiaryCollection),
    returns: readList(record, 'returns', path, readDiaryReturn),
  }
}

function readDiary(value: unknown, path: string): BranchDiary {
  const record = readObject(value, path, 'a branch diary')
  return {
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    days: readList(record, 'days', path, readDiaryDay),
  }
}

/**
 * GET /api/counter/dashboard. What is due today at one branch.
 *
 * @throws ApiError with status 403 when counter staff name another branch, and
 *   422 when an administrator names none.
 */
export function getCounterDashboard(query: DashboardQuery, signal?: AbortSignal): Promise<CounterDashboard> {
  return api.get(DASHBOARD_ENDPOINT, readDashboard, { query, signal })
}

/**
 * GET /api/counter/diary. One day, or up to seven in a row, at one branch.
 *
 * @throws ApiError with status 403 when counter staff name another branch, and
 *   422 when the first day or the number of days is refused.
 */
export function getBranchDiary(query: DiaryQuery, signal?: AbortSignal): Promise<BranchDiary> {
  return api.get(DIARY_ENDPOINT, readDiary, { query, signal })
}
