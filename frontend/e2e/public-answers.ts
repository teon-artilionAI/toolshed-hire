/**
 * The API answered by the spec itself, for the catalogue a visitor reads.
 *
 * The accessibility scan and the layout check of SC-01, SC-02 and SC-03 need
 * branches, categories, models, an availability search, one model in full,
 * what each branch says about it and the server's price. A scan should not
 * depend on what a database happens to hold, and it should run with or
 * without a backend, so these answers stand in for the API. They are shaped
 * the way the contract describes them, with long names and large figures,
 * which are what break a layout. customer-answers.ts answers the screens a
 * signed in customer reads, and takes these as well.
 */

import { dateFromToday } from './hire-dates.ts'

/** The model the detail screen and the basket open. */
export const MODEL_SLUG = 'cp-100-plate-compactor'

/** Its name, which is the heading of SC-03. */
export const MODEL_NAME = 'Wacker Neuson CP 100 Plate Compactor with Water Tank and Wheel Kit'

/** The dates every catalogue answer is for, a week out. */
export const HIRE_FROM = dateFromToday(7)
export const HIRE_TO = dateFromToday(11)

export const BRANCHES = {
  items: [
    { code: 'CBD', name: 'Cape Town CBD', suburb: 'Woodstock', city: 'Cape Town', phone: '021 555 0142', opensAt: '07:00', closesAt: '17:00' },
    { code: 'BLV', name: 'Bellville', suburb: 'Stikland', city: 'Cape Town', phone: '021 555 0157', opensAt: '07:00', closesAt: '17:00' },
    { code: 'SMW', name: 'Somerset West', suburb: 'Firgrove', city: 'Cape Town', phone: '021 555 0163', opensAt: '07:00', closesAt: '17:00' },
  ],
}

const CATEGORIES = {
  items: [
    { code: 'COMPACTION', name: 'Compaction and Earthmoving', slug: 'compaction', description: 'Plate compactors, rammers and rollers for trenches and driveways.', parentCode: null, sortOrder: 20, modelCount: 2 },
    { code: 'ACCESS-LIFT', name: 'Access, Lifting and Working at Height Equipment', slug: 'access-lifting', description: 'Working at height and lifting.', parentCode: null, sortOrder: 60, modelCount: 1 },
    { code: 'ACCESS', name: 'Ladders, Trestles and Mobile Scaffold Towers', slug: 'ladders-trestles-towers', description: '', parentCode: 'ACCESS-LIFT', sortOrder: 61, modelCount: 1 },
  ],
}

function model(slug: string, name: string, overrides: Record<string, unknown> = {}) {
  return {
    sku: `SKU-${slug.toUpperCase()}`,
    slug,
    name,
    manufacturer: 'Wacker Neuson Produktion GmbH und Co. KG',
    modelNumber: 'CP 100 Mk II',
    categoryCode: 'COMPACTION',
    categoryName: 'Compaction and Earthmoving',
    shortDescription: 'Forward plate compactor, 62 kg, 500 mm plate, with a water tank for asphalt and paving.',
    dailyRate: '12340.00',
    weeklyRate: '49360.00',
    depositAmount: '125000.00',
    minHireDays: 1,
    maxHireDays: 28,
    imagePath: null,
    ...overrides,
  }
}

const COMPACTOR = model(MODEL_SLUG, MODEL_NAME)
const RAMMER = model('bs-60-4-trench-rammer', 'Wacker Neuson BS 60-4 Trench Rammer for Narrow Trenches and Backfill', {
  dailyRate: '395.00',
  weeklyRate: '1580.00',
  depositAmount: '1800.00',
})
const LADDER = model('extension-ladder-7m', 'Extension Ladder Seven Metre Aluminium Triple Section', {
  categoryCode: 'ACCESS',
  categoryName: 'Ladders, Trestles and Mobile Scaffold Towers',
  dailyRate: '95.00',
  weeklyRate: '380.00',
  depositAmount: '500.00',
})

function branchAnswers(cbd: boolean, blv: boolean, smw: boolean) {
  return [
    { branchCode: 'CBD', branchName: 'Cape Town CBD', available: cbd },
    { branchCode: 'BLV', branchName: 'Bellville', available: blv },
    { branchCode: 'SMW', branchName: 'Somerset West', available: smw },
  ]
}

/** Four days of the compactor, priced the way the quote route sends it. */
const QUOTE = {
  from: HIRE_FROM,
  to: HIRE_TO,
  hireDays: 4,
  quantity: 1,
  perUnit: { dailyRate: '12340.00', weeklyRate: '49360.00', wholeWeeks: 0, remainderDays: 4, basis: 'daily', amountExVat: '49360.00' },
  subtotalExVat: '49360.00',
  discountPercent: '10.00',
  discountAmount: '4936.00',
  vatRate: '15.00',
  vatAmount: '6663.60',
  totalIncVat: '51087.60',
  depositPerUnit: '125000.00',
  depositTotal: '125000.00',
  lateFeePerDay: '9876.54',
}

/** An availability search with these models free or not. */
export function availabilityOf(items: readonly { model: unknown; branches: unknown }[]) {
  return { from: HIRE_FROM, to: HIRE_TO, hireDays: 4, items, page: 1, pageSize: 24, total: items.length }
}

/** What each catalogue route answers, by method and path. */
export const PUBLIC_ANSWERS: Record<string, unknown> = {
  'GET /api/branches': BRANCHES,
  'GET /api/catalogue/categories': CATEGORIES,
  'GET /api/catalogue/models': { items: [COMPACTOR, RAMMER, LADDER], page: 1, pageSize: 6, total: 120 },
  'GET /api/catalogue/availability': availabilityOf([
    { model: COMPACTOR, branches: branchAnswers(true, true, false) },
    { model: RAMMER, branches: branchAnswers(false, true, false) },
    { model: LADDER, branches: branchAnswers(false, false, false) },
  ]),
  [`GET /api/catalogue/models/${MODEL_SLUG}`]: {
    ...COMPACTOR,
    longDescription: 'The handle folds so it fits in a bakkie. The water tank stops asphalt sticking to the plate.',
    lateFeePerDay: '9876.54',
  },
  [`GET /api/catalogue/models/${MODEL_SLUG}/availability`]: {
    from: HIRE_FROM,
    to: HIRE_TO,
    hireDays: 4,
    quantity: 1,
    branches: branchAnswers(true, false, false),
  },
  [`GET /api/catalogue/models/${MODEL_SLUG}/quote`]: QUOTE,
}
