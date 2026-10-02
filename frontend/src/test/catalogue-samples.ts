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
