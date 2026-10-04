/**
 * The API answered by the spec itself, for the owner's staff accounts and
 * customer holds on SC-23.
 *
 * The accessibility scan and the narrow screen check of SC-23 need a signed in
 * owner, staff accounts in every kind of standing and customers in every
 * standing. They answer beside the dashboard and the report in
 * admin-answers.ts, with long names, long addresses and a company name that
 * runs on, which are what break a layout. One account is the owner's own, one
 * is locked and has never signed in, and one is deactivated.
 */

/** The owner's key, the same one the session in admin-answers.ts carries. */
const OWNER_ID = '0b0f6f3e-1111-4a2b-9c3d-000000000005'

/** The account the scans open, by the name at the head of its row. */
export const LOCKED_ACCOUNT_NAME = 'Nomvuyiso Thandiwe Mahlangu-Vanderbijl'

/** The customer the scans move, by the name at the head of the entry. */
export const HELD_CUSTOMER_NAME = 'Bartholomew Christiaan van der Westhuizen-Mokoena'

/** A year, in milliseconds. */
const A_YEAR_MS = 31_536_000_000

/** A lock that ends a year from now, so the scan sees an account still locked. */
const LOCKED_UNTIL = new Date(Date.now() + A_YEAR_MS).toISOString()

function account(id: string, overrides: Record<string, unknown>) {
  return {
    id: `0b0f6f3e-1111-4a2b-9c3d-0000000000${id}`,
    email: 'counter.assistant.with.a.long.address@toolshedhire-capetown-branches.co.za',
    fullName: 'Counter Assistant',
    phone: '0215550142',
    role: 'COUNTER_STAFF',
    branchCode: 'CBD',
    isActive: true,
    emailVerified: true,
    lastLoginAt: '2026-10-03T07:45:00+02:00',
    lockedUntil: null,
    createdAt: '2024-01-10T09:00:00+02:00',
    ...overrides,
  }
}

const ACCOUNTS = {
  items: [
    account('05', {
      id: OWNER_ID,
      email: 'marius@toolshedhire.co.za',
      fullName: 'Marius Pretorius-Vanderwesthuizen',
      role: 'ADMIN',
      branchCode: null,
    }),
    account('12', {
      fullName: LOCKED_ACCOUNT_NAME,
      branchCode: 'BLV',
      phone: null,
      emailVerified: false,
      lastLoginAt: null,
      lockedUntil: LOCKED_UNTIL,
    }),
    account('13', { fullName: 'Andre Klaasen', branchCode: 'SMW', isActive: false }),
  ],
  page: 1,
  pageSize: 20,
  total: 46,
}

function customer(id: string, overrides: Record<string, unknown>) {
  return {
    id: `7a1d0c4e-0000-4000-8000-000000000${id}`,
    displayName: HELD_CUSTOMER_NAME,
    email: 'bartholomew.vanderwesthuizen-mokoena@buildright-construction-and-civils.co.za',
    phone: '0824417719',
    hasLogin: true,
    emailVerified: true,
    customerType: 'TRADE',
    companyName: 'BuildRight Construction and Civils (Pty) Ltd, Montague Gardens Industrial Park',
    idDocumentType: 'SA_ID',
    idDocumentLast4: '5083',
    billingSuburb: 'Montague Gardens',
    billingCity: 'Cape Town',
    accountStatus: 'ON_HOLD',
    tradeDiscountPercent: '10.00',
    noShowCount: 3,
    homeBranchCode: 'SMW',
    ...overrides,
  }
}

const CUSTOMERS = {
  items: [
    customer('401', {}),
    customer('402', { displayName: 'Thandi Mokoena', email: null, hasLogin: false, customerType: 'INDIVIDUAL', companyName: null, accountStatus: 'ACTIVE', noShowCount: 0 }),
    customer('403', { displayName: 'Riaan van Wyk', accountStatus: 'BLACKLISTED', noShowCount: 1 }),
  ],
  page: 1,
  pageSize: 20,
  total: 45,
}

/** What the routes of SC-23 answer. */
export const USER_ANSWERS: Record<string, unknown> = {
  'GET /api/admin/users': ACCOUNTS,
  'GET /api/admin/customers': CUSTOMERS,
}
