/**
 * The screen inventory, as a single source of truth.
 *
 * Every entry maps one to one onto a screen in the Task 1 journey map, and
 * the SC identifiers are carried through to the interface itself. That
 * matters because the documentation, the prototype and the built system are
 * all marked on reconciling with each other, and a screen that exists in
 * one and not the others is a finding.
 */

import type { Role } from './types'

export interface ScreenDef {
  /** Identifier from the documented screen inventory, for example SC-01.
   *  A development screen carries a DEV- identifier instead, see `devOnly`. */
  id: string
  path: string
  name: string
  /** Short label for navigation, where the full name is too long. */
  navLabel?: string
  role: Role
  /** Reachable without signing in. */
  publicAccess?: boolean
  /** Shown in the primary navigation rather than reached from another screen. */
  inNav?: boolean
  icon?: string
  /**
   * A development and demonstration screen, not part of the assessed
   * inventory. It is routed from this table like everything else, because one
   * routing table is the point, but it is never counted among the twenty four,
   * never captured into the document appendix, and never listed as a screen of
   * the product.
   */
  devOnly?: boolean
}

export const SCREENS: ScreenDef[] = [
  // Customer, SC-01 to SC-09
  { id: 'SC-01', path: '/', name: 'Catalogue Home', navLabel: 'Catalogue', role: 'customer', publicAccess: true, inNav: true, icon: 'Home' },
  { id: 'SC-02', path: '/search', name: 'Availability Search Results', navLabel: 'Search', role: 'customer', publicAccess: true, inNav: true, icon: 'Search' },
  { id: 'SC-03', path: '/model/:modelId', name: 'Product Model Detail', role: 'customer', publicAccess: true },
  { id: 'SC-04', path: '/basket', name: 'Hire Basket and Booking Review', navLabel: 'Basket', role: 'customer', publicAccess: true, inNav: true, icon: 'ShoppingCart' },
  { id: 'SC-05', path: '/register', name: 'Register', role: 'customer', publicAccess: true },
  { id: 'SC-06', path: '/signin', name: 'Sign In and Password Reset', role: 'customer', publicAccess: true },
  { id: 'SC-07', path: '/reservations', name: 'My Reservations', navLabel: 'My Hires', role: 'customer', inNav: true, icon: 'CalendarDays' },
  { id: 'SC-08', path: '/reservations/:reservationId', name: 'Reservation Detail and Cancellation', role: 'customer' },
  { id: 'SC-09', path: '/account', name: 'My Account and Hire History', navLabel: 'Account', role: 'customer', inNav: true, icon: 'User' },

  // Counter staff, SC-10 to SC-18
  { id: 'SC-10', path: '/counter', name: 'Counter Dashboard', navLabel: 'Today', role: 'counter', inNav: true, icon: 'LayoutDashboard' },
  { id: 'SC-11', path: '/counter/diary', name: 'Branch Diary', navLabel: 'Diary', role: 'counter', inNav: true, icon: 'CalendarRange' },
  { id: 'SC-12', path: '/counter/customers', name: 'Customer Lookup and Walk-in Registration', navLabel: 'Customers', role: 'counter', inNav: true, icon: 'Users' },
  { id: 'SC-13', path: '/counter/booking', name: 'New Booking and Asset Allocation', navLabel: 'New Booking', role: 'counter', inNav: true, icon: 'CalendarPlus' },
  { id: 'SC-14', path: '/counter/checkout/:rentalId', name: 'Checkout and Deposit', role: 'counter' },
  { id: 'SC-15', path: '/counter/return/:rentalId', name: 'Return and Condition Inspection', role: 'counter' },
  { id: 'SC-16', path: '/counter/damage/:assetId', name: 'Damage Report Capture', role: 'counter' },
  { id: 'SC-17', path: '/counter/locator', name: 'Asset Locator', navLabel: 'Locator', role: 'counter', inNav: true, icon: 'MapPin' },
  { id: 'SC-18', path: '/counter/overdue', name: 'Overdue and Late Fee Worklist', navLabel: 'Overdue', role: 'counter', inNav: true, icon: 'AlarmClock' },

  // Admin and owner, SC-19 to SC-24
  { id: 'SC-19', path: '/admin', name: 'Admin Dashboard', navLabel: 'Overview', role: 'admin', inNav: true, icon: 'LayoutDashboard' },
  { id: 'SC-20', path: '/admin/catalogue', name: 'Catalogue and Pricing Management', navLabel: 'Catalogue', role: 'admin', inNav: true, icon: 'Tags' },
  { id: 'SC-21', path: '/admin/assets', name: 'Asset Register and Lifecycle', navLabel: 'Assets', role: 'admin', inNav: true, icon: 'Boxes' },
  { id: 'SC-22', path: '/admin/reports', name: 'Utilisation and Gross Contribution Report', navLabel: 'Reports', role: 'admin', inNav: true, icon: 'BarChart3' },
  { id: 'SC-23', path: '/admin/users', name: 'User and Role Management', navLabel: 'Users', role: 'admin', inNav: true, icon: 'ShieldCheck' },
  { id: 'SC-24', path: '/admin/audit', name: 'Audit and Notification Log', navLabel: 'Audit', role: 'admin', inNav: true, icon: 'ScrollText' },

  // Development and demonstration. Not one of the twenty-four assessed screens.
  // The identifier stays outside the SC series so the numbered inventory remains
  // stable and maps one-to-one to the interface specification.
  //
  // It is reached by typing /system. It is deliberately absent from every
  // navigation menu, because a demonstration screen in the product's own
  // navigation reads as part of the product.
  { id: 'DEV-01', path: '/system', name: 'System Connectivity', role: 'customer', publicAccess: true, devOnly: true },
]

/**
 * The screens belonging to a role.
 *
 * Development screens are excluded. This function answers a question about the
 * product, and the count it returns is one of the things the documentation is
 * reconciled against.
 */
export function screensForRole(role: Role): ScreenDef[] {
  return SCREENS.filter((s) => s.role === role && !s.devOnly)
}

export function navForRole(role: Role): ScreenDef[] {
  return SCREENS.filter((s) => s.role === role && s.inNav)
}

export function screenById(id: string): ScreenDef | undefined {
  return SCREENS.find((s) => s.id === id)
}

export const ROLE_LABEL: Record<Role, string> = {
  customer: 'Customer',
  counter: 'Counter Staff',
  admin: 'Admin and Owner',
}

/** Landing path when a role signs in. */
export const ROLE_HOME: Record<Role, string> = {
  customer: '/',
  counter: '/counter',
  admin: '/admin',
}
