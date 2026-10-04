/**
 * The API answered by the spec itself, for the owner's asset register on
 * SC-21.
 *
 * The accessibility scan and the narrow screen check of SC-21 need a signed in
 * owner and units in every kind of standing, one on the shelf with open damage
 * reports and a booking holding it, one at intake and one retired. They answer
 * beside the dashboard and the report in admin-answers.ts, with the longest
 * tag the register takes, long names, a long serial number and long notes,
 * which are what break a layout. The unit on the shelf also answers its own
 * read with a history of every kind, so the unit is scanned and measured open.
 */

/** The unit whose section the scans open. Sixteen characters, the longest tag there is. */
export const ASSET_TAG = 'TSH-SCAF-T-00126'

const MODEL_ID = 'a0de1000-0000-4000-8000-000000000124'

function unit(tag: string, overrides: Record<string, unknown>) {
  return {
    id: `a55e7000-0000-4000-8000-0000000${tag.slice(-5)}`,
    assetTag: tag,
    modelId: MODEL_ID,
    modelName: 'Youngman BoSS Clima 500 Mobile Aluminium Scaffold Tower, 6.2 m Working Height',
    modelSlug: 'boss-clima-500-scaffold-tower',
    categoryName: 'Ladders, Trestles and Mobile Scaffold Towers',
    branchCode: 'CBD',
    branchName: 'Cape Town CBD and Foreshore',
    serialNumber: 'YNG-BOSS-CLIMA-500-2026-0000123456789',
    status: 'AVAILABLE',
    conditionGrade: 'B',
    acquiredOn: '2024-06-11',
    acquisitionCost: '1234567.89',
    hourMeterReading: 2147483,
    notes:
      'Guard rail clamps replaced after the Stellenbosch job. Stabilisers stored separately in bay fourteen, labelled with the tag of this tower.',
    retiredOn: null,
    activeAllocationCount: 12,
    openDamageReports: 3,
    allowedTransitions: ['QUARANTINED', 'UNDER_REPAIR', 'RETIRED'],
    ...overrides,
  }
}

const SHELF = unit(ASSET_TAG, {})

const HISTORY = [
  {
    at: '2026-10-03T09:15:00+02:00',
    kind: 'ALLOCATION',
    summary: 'Held for booking TSH-R-26-000124 from 2026-10-12 to 2026-10-16.',
    reference: 'TSH-R-26-000124',
  },
  {
    at: '2026-09-21T16:40:00+02:00',
    kind: 'DAMAGE_REPORT',
    summary: 'Damage report TSH-D-26-00031 filed for damage beyond repair.',
    reference: 'TSH-D-26-00031',
  },
  {
    at: '2026-09-02T08:05:00+02:00',
    kind: 'RENTAL',
    summary: 'Handed over on hire TSH-H-26-000099 in grade B, due back 2026-09-09.',
    reference: 'TSH-H-26-000099',
  },
  {
    at: '2024-06-11T10:00:00+02:00',
    kind: 'AUDIT_EVENT',
    summary:
      'Moved from QUARANTINED to AVAILABLE. Inspected by the workshop after the Stellenbosch job and found sound, so back on the shelf.',
    reference: null,
  },
]

const UNITS = {
  items: [
    SHELF,
    unit('TSH-SCAF-T-00127', { status: 'INTAKE', serialNumber: null, hourMeterReading: null, notes: null, activeAllocationCount: 0, openDamageReports: 0, allowedTransitions: ['AVAILABLE', 'QUARANTINED'] }),
    unit('TSH-SCAF-T-00003', { status: 'RETIRED', retiredOn: '2026-02-28', openDamageReports: 0, activeAllocationCount: 0, allowedTransitions: [] }),
  ],
  page: 1,
  pageSize: 20,
  total: 126,
}

/** What the routes of SC-21 answer. */
export const ASSET_ANSWERS: Record<string, unknown> = {
  'GET /api/admin/assets': UNITS,
  [`GET /api/admin/assets/${ASSET_TAG}`]: { ...SHELF, history: HISTORY },
}
