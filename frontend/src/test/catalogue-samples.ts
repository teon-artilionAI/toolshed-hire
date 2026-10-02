/**
 * Sample API answers for the catalogue tests.
 *
 * These are bodies exactly as the contract describes them, with money as
 * strings and every branch present for every model. They are test data only.
 * No screen imports them.
 */

import type {
  AvailabilityPage,
  BranchAvailability,
  BranchList,
  CategoryList,
  ModelAvailability,
  ModelDetail,
  ModelPage,
  ModelQuote,
  ModelSummary,
} from '../shared/api/contract'

/** The instant the screen tests pin the clock to. Morning in Cape Town. */
export const TEST_NOW = new Date('2026-03-12T08:00:00+02:00')

/** Today and the default return date at `TEST_NOW`, in branch time. */
export const TEST_TODAY = '2026-03-12'
export const TEST_DEFAULT_RETURN = '2026-03-16'

export const BRANCHES: BranchList = {
  items: [
    { code: 'CBD', name: 'Cape Town CBD', suburb: 'Woodstock', city: 'Cape Town', phone: '021 555 0142', opensAt: '07:00', closesAt: '17:00' },
    { code: 'BLV', name: 'Bellville', suburb: 'Stikland', city: 'Cape Town', phone: '021 555 0157', opensAt: '07:00', closesAt: '17:00' },
    { code: 'SMW', name: 'Somerset West', suburb: 'Firgrove', city: 'Cape Town', phone: '021 555 0163', opensAt: '07:00', closesAt: '17:00' },
  ],
}

/** A parent's count includes its children, the way the API sends it. The last
 *  one has no description, which arrives as an empty string. */
export const CATEGORIES: CategoryList = {
  items: [
    { code: 'COMPACTION', name: 'Compaction', slug: 'compaction', description: 'Plate compactors and rammers.', parentCode: null, sortOrder: 20, modelCount: 2 },
    { code: 'ACCESS-LIFT', name: 'Access and Lifting', slug: 'access-lifting', description: 'Working at height and lifting.', parentCode: null, sortOrder: 60, modelCount: 1 },
    { code: 'ACCESS', name: 'Ladders, Trestles and Towers', slug: 'ladders-trestles-towers', description: '', parentCode: 'ACCESS-LIFT', sortOrder: 61, modelCount: 1 },
  ],
}

export const PLATE_COMPACTOR: ModelSummary = {
  sku: 'PC-WACKER-CP100',
  slug: 'cp-100-plate-compactor',
  name: 'CP 100 Plate Compactor',
  manufacturer: 'Wacker Neuson',
  modelNumber: 'CP 100',
  categoryCode: 'COMPACTION',
  categoryName: 'Compaction',
  shortDescription: 'Forward plate compactor, 62 kg, 500 mm plate.',
  dailyRate: '340.00',
  weeklyRate: '1360.00',
  depositAmount: '1500.00',
  minHireDays: 1,
  maxHireDays: 28,
  imagePath: null,
}

export const TRENCH_RAMMER: ModelSummary = {
  sku: 'RM-WACKER-BS604',
  slug: 'bs-60-4-trench-rammer',
  name: 'BS 60-4 Trench Rammer',
  manufacturer: 'Wacker Neuson',
  modelNumber: 'BS 60-4',
  categoryCode: 'COMPACTION',
  categoryName: 'Compaction',
  shortDescription: 'Upright rammer for narrow trenches.',
  dailyRate: '395.00',
  weeklyRate: '1580.00',
  depositAmount: '1800.00',
  minHireDays: 1,
  maxHireDays: 28,
  imagePath: null,
}

export const PLATE_COMPACTOR_DETAIL: ModelDetail = {
  ...PLATE_COMPACTOR,
  longDescription: 'The handle folds so it fits in a bakkie.',
  lateFeePerDay: '220.00',
}

export const MODEL_PAGE: ModelPage = {
  items: [PLATE_COMPACTOR, TRENCH_RAMMER],
  page: 1,
  pageSize: 6,
  total: 120,
}

/** A yes or no from each of the three branches, in branch order. */
export function branchAnswers(cbd: boolean, blv: boolean, smw: boolean): BranchAvailability[] {
  return [
    { branchCode: 'CBD', branchName: 'Cape Town CBD', available: cbd },
    { branchCode: 'BLV', branchName: 'Bellville', available: blv },
    { branchCode: 'SMW', branchName: 'Somerset West', available: smw },
  ]
}

export const AVAILABILITY_PAGE: AvailabilityPage = {
  from: TEST_TODAY,
  to: TEST_DEFAULT_RETURN,
  hireDays: 4,
  items: [
    { model: PLATE_COMPACTOR, branches: branchAnswers(true, true, false) },
    { model: TRENCH_RAMMER, branches: branchAnswers(false, true, false) },
  ],
  page: 1,
  pageSize: 24,
  total: 2,
}

export const EMPTY_AVAILABILITY_PAGE: AvailabilityPage = {
  ...AVAILABILITY_PAGE,
  items: [],
  total: 0,
}

export const MODEL_AVAILABILITY: ModelAvailability = {
  from: TEST_TODAY,
  to: TEST_DEFAULT_RETURN,
  hireDays: 4,
  quantity: 1,
  branches: branchAnswers(true, false, false),
}

/** Four days of one plate compactor. Too short for a week, so every day is
 *  charged at the daily rate. */
export const DAILY_QUOTE: ModelQuote = {
  from: TEST_TODAY,
  to: TEST_DEFAULT_RETURN,
  hireDays: 4,
  quantity: 1,
  perUnit: {
    dailyRate: '340.00',
    weeklyRate: '1360.00',
    wholeWeeks: 0,
    remainderDays: 4,
    basis: 'daily',
    amountExVat: '1360.00',
  },
  subtotalExVat: '1360.00',
  discountPercent: '0.00',
  discountAmount: '0.00',
  vatRate: '15.00',
  vatAmount: '204.00',
  totalIncVat: '1564.00',
  depositPerUnit: '1500.00',
  depositTotal: '1500.00',
  lateFeePerDay: '220.00',
}

/** The day ten days after `TEST_TODAY`, which makes a week and three days. */
export const TEST_TEN_DAY_RETURN = '2026-03-22'

/** Ten days of two plate compactors. A whole week at the weekly rate and the
 *  three days left over at the daily rate. */
export const WEEKLY_QUOTE: ModelQuote = {
  from: TEST_TODAY,
  to: TEST_TEN_DAY_RETURN,
  hireDays: 10,
  quantity: 2,
  perUnit: {
    dailyRate: '340.00',
    weeklyRate: '1360.00',
    wholeWeeks: 1,
    remainderDays: 3,
    basis: 'weekly',
    amountExVat: '2380.00',
  },
  subtotalExVat: '4760.00',
  discountPercent: '0.00',
  discountAmount: '0.00',
  vatRate: '15.00',
  vatAmount: '714.00',
  totalIncVat: '5474.00',
  depositPerUnit: '1500.00',
  depositTotal: '3000.00',
  lateFeePerDay: '220.00',
}
