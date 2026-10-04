/**
 * The API answered by the spec itself, for the owner's catalogue on SC-20.
 *
 * The accessibility scan and the narrow screen check of SC-20 need a signed in
 * owner, categories at both levels with one switched off, and models published
 * and hidden. They answer beside the dashboard and the report in
 * admin-answers.ts, with long names, long codes and large figures, which are
 * what break a layout. One model also answers its own read, so the form is
 * scanned and measured open.
 */

/** The key of the model whose form the scans open. */
export const CATALOGUE_MODEL_ID = 'a0de1000-0000-4000-8000-000000000124'

const TOP = 'ca700000-0000-4000-8000-000000000001'

function category(id: string, overrides: Record<string, unknown>) {
  return {
    id,
    code: 'ACCESS-LIFT',
    name: 'Access, Lifting and Working at Height Equipment',
    slug: 'access-lifting-working-at-height',
    description: null,
    parentCategoryId: null,
    parentName: null,
    sortOrder: 60,
    isActive: true,
    modelCount: 0,
    ...overrides,
  }
}

const CATEGORIES = {
  items: [
    category(TOP, {}),
    category('ca700000-0000-4000-8000-000000000002', {
      code: 'ACCESS-TOWER',
      name: 'Ladders, Trestles and Mobile Scaffold Towers',
      slug: 'ladders-trestles-towers',
      parentCategoryId: TOP,
      parentName: 'Access, Lifting and Working at Height Equipment',
      sortOrder: 61,
      modelCount: 2,
    }),
    category('ca700000-0000-4000-8000-000000000003', {
      code: 'WELD-FAB',
      name: 'Welding and Fabrication',
      slug: 'welding-fabrication',
      sortOrder: 90,
      isActive: false,
    }),
  ],
  page: 1,
  pageSize: 100,
  total: 3,
}

function model(id: string, overrides: Record<string, unknown>) {
  return {
    id,
    sku: 'AC-YOUNGMAN-BOSS-CLIMA',
    name: 'Youngman BoSS Clima 500 Mobile Aluminium Scaffold Tower, 6.2 m Working Height',
    slug: 'boss-clima-500-scaffold-tower',
    categoryId: 'ca700000-0000-4000-8000-000000000002',
    categoryName: 'Ladders, Trestles and Mobile Scaffold Towers',
    manufacturer: 'Youngman',
    modelNumber: 'BoSS Clima 500',
    shortDescription: 'Mobile aluminium tower with stabilisers and guard rails, erected by one trained person.',
    longDescription: null,
    dailyRate: '1234.56',
    weeklyRate: '7890.12',
    depositAmount: '25000.00',
    lateFeePerDay: '987.65',
    replacementValue: '1234567.89',
    minHireDays: 1,
    maxHireDays: 28,
    isPublished: true,
    assetCount: 126,
    updatedAt: '2026-10-03T15:30:00+02:00',
    ...overrides,
  }
}

const SCAFFOLD = model(CATALOGUE_MODEL_ID, {})

const MODELS = {
  items: [
    SCAFFOLD,
    model('a0de1000-0000-4000-8000-000000000125', {
      sku: 'AC-WERNER-TRIPLE-EXT-7M',
      name: 'Werner Extension Ladder Seven Metre Aluminium Triple Section',
      slug: 'werner-extension-ladder-7m',
      isPublished: false,
      assetCount: 0,
    }),
  ],
  page: 1,
  pageSize: 20,
  total: 46,
}

/** What the routes of SC-20 answer. */
export const CATALOGUE_ANSWERS: Record<string, unknown> = {
  'GET /api/admin/categories': CATEGORIES,
  'GET /api/admin/models': MODELS,
  [`GET /api/admin/models/${CATALOGUE_MODEL_ID}`]: SCAFFOLD,
}
