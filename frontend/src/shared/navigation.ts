/**
 * The screen inventory, as a single source of truth.
 *
 * Every entry maps one to one onto a screen in the journey map, and the SC
 * identifiers are carried through to the interface itself. That matters
 * because the documentation, the prototype and the built system have to
 * reconcile with each other, and a screen that exists in one and not the
 * others is a finding.
 *
 * Three things are decided from this table and from nowhere else. The router
 * takes its routes from it. The guards take from it who may open a screen,
 * through `publicAccess` and `role`. The shell takes from it whether a screen
 * is connected to the API yet, through `live`. The rules that read the table
 * are in screen-access.ts.
 */

import type { Role } from './types'

export interface ScreenDef {
  /** Identifier from the documented screen inventory, for example SC-01.
   *  A development screen carries a DEV- identifier instead, see `devOnly`,
   *  and a supporting page an INFO- one, see `supporting`. */
  id: string
  path: string
  name: string
  /** Short label for navigation, where the full name is too long. */
  navLabel?: string
  /** The area the screen belongs to. Unless the screen is public, only a
   *  person whose role reaches that area may open it. */
  role: Role
  /** Reachable without signing in, and by every role. */
  publicAccess?: boolean
  /**
   * Whether the screen reads from the API.
   *
   * False means it still shows sample data, and the shell says so above the
   * screen. Connecting a screen means changing this to true and nothing else.
   */
  live: boolean
  /** Shown in the primary navigation rather than reached from another screen. */
  inNav?: boolean
  icon?: string
  /**
   * A development screen, not one of the numbered screens. It is routed from
   * this table like everything else, because one routing table is the point,
   * but it is never counted among the twenty four, never shown in a menu, and
   * never listed as a screen of the product.
   */
  devOnly?: boolean
  /**
   * A page the product needs that is not one of the numbered screens, such as
   * the privacy notice. It is routed and guarded from this table like every
   * screen. It is never counted among the twenty four and never shown in a
   * menu. The shell links to it from the footer of every screen.
   */
  supporting?: boolean
}

export const SCREENS: ScreenDef[] = [
  // Customer, SC-01 to SC-09
  { id: 'SC-01', path: '/', name: 'Catalogue Home', navLabel: 'Catalogue', role: 'customer', publicAccess: true, live: true, inNav: true, icon: 'Home' },
  { id: 'SC-02', path: '/search', name: 'Availability Search Results', navLabel: 'Search', role: 'customer', publicAccess: true, live: true, inNav: true, icon: 'Search' },
  { id: 'SC-03', path: '/model/:slug', name: 'Product Model Detail', role: 'customer', publicAccess: true, live: true },
  { id: 'SC-04', path: '/basket', name: 'Hire Basket and Booking Review', navLabel: 'Basket', role: 'customer', publicAccess: true, live: true, inNav: true, icon: 'ShoppingCart' },
  { id: 'SC-05', path: '/register', name: 'Register', role: 'customer', publicAccess: true, live: true },
  { id: 'SC-06', path: '/signin', name: 'Sign In and Password Reset', role: 'customer', publicAccess: true, live: true },
  { id: 'SC-07', path: '/reservations', name: 'My Reservations', navLabel: 'My Hires', role: 'customer', live: true, inNav: true, icon: 'CalendarDays' },
  { id: 'SC-08', path: '/reservations/:reservationId', name: 'Reservation Detail and Cancellation', role: 'customer', live: true },
  { id: 'SC-09', path: '/account', name: 'My Account and Hire History', navLabel: 'Account', role: 'customer', live: true, inNav: true, icon: 'User' },

  // Counter staff, SC-10 to SC-18
  { id: 'SC-10', path: '/counter', name: 'Counter Dashboard', navLabel: 'Today', role: 'counter', live: true, inNav: true, icon: 'LayoutDashboard' },
  { id: 'SC-11', path: '/counter/diary', name: 'Branch Diary', navLabel: 'Diary', role: 'counter', live: true, inNav: true, icon: 'CalendarRange' },
  { id: 'SC-12', path: '/counter/customers', name: 'Customer Lookup and Walk-in Registration', navLabel: 'Customers', role: 'counter', live: true, inNav: true, icon: 'Users' },
  { id: 'SC-13', path: '/counter/booking', name: 'New Booking and Asset Allocation', navLabel: 'New Booking', role: 'counter', live: true, inNav: true, icon: 'CalendarPlus' },
  // The value is the key of a reservation or its reference, because a checkout
  // hands a confirmed reservation over and makes the hire from it.
  { id: 'SC-14', path: '/counter/checkout/:reservationId', name: 'Checkout and Deposit', role: 'counter', live: true },
  // The value is the key of a hire or its reference. Every link to it carries
  // the key, and a reference typed from the paperwork works too.
  { id: 'SC-15', path: '/counter/return/:rentalId', name: 'Return and Condition Inspection', role: 'counter', live: true },
  // The value is the tag of a unit. A link from a return also carries the unit
  // of the hire it came back on, as `?rentalItem=`.
  { id: 'SC-16', path: '/counter/damage/:assetTag', name: 'Damage Report Capture', role: 'counter', live: true },
  { id: 'SC-17', path: '/counter/locator', name: 'Asset Locator', navLabel: 'Locator', role: 'counter', live: true, inNav: true, icon: 'MapPin' },
  { id: 'SC-18', path: '/counter/overdue', name: 'Overdue and Late Fee Worklist', navLabel: 'Overdue', role: 'counter', live: true, inNav: true, icon: 'AlarmClock' },

  // Admin and owner, SC-19 to SC-24
  { id: 'SC-19', path: '/admin', name: 'Admin Dashboard', navLabel: 'Overview', role: 'admin', live: false, inNav: true, icon: 'LayoutDashboard' },
  { id: 'SC-20', path: '/admin/catalogue', name: 'Catalogue and Pricing Management', navLabel: 'Catalogue', role: 'admin', live: false, inNav: true, icon: 'Tags' },
  { id: 'SC-21', path: '/admin/assets', name: 'Asset Register and Lifecycle', navLabel: 'Assets', role: 'admin', live: false, inNav: true, icon: 'Boxes' },
  { id: 'SC-22', path: '/admin/reports', name: 'Utilisation and Gross Contribution Report', navLabel: 'Reports', role: 'admin', live: false, inNav: true, icon: 'BarChart3' },
  { id: 'SC-23', path: '/admin/users', name: 'User and Role Management', navLabel: 'Users', role: 'admin', live: false, inNav: true, icon: 'ShieldCheck' },
  { id: 'SC-24', path: '/admin/audit', name: 'Audit and Notification Log', navLabel: 'Audit', role: 'admin', live: false, inNav: true, icon: 'ScrollText' },

  // Supporting pages. Not among the twenty-four numbered screens.
  // The identifier stays outside the SC series for the same reason the
  // development screen's does, so the numbered inventory still maps one-to-one
  // to the interface specification.
  //
  // The privacy notice is public, because a visitor has to be able to read it
  // before they register. It holds words and no data, so it counts as live.
  { id: 'INFO-01', path: '/privacy', name: 'Privacy Notice', role: 'customer', publicAccess: true, live: true, supporting: true },

  // Development. Not one of the twenty-four numbered screens.
  // The identifier stays outside the SC series so the numbered inventory remains
  // stable and maps one-to-one to the interface specification.
  //
  // It is reached by typing /system. It is deliberately absent from every
  // navigation menu, because a development screen in the product's own
  // navigation reads as part of the product. It reads only from the API and
  // shows no sample data, so it counts as live.
  { id: 'DEV-01', path: '/system', name: 'System Connectivity', role: 'customer', publicAccess: true, live: true, devOnly: true },
]

/**
 * The screens belonging to a role.
 *
 * Development screens and supporting pages are excluded. This function answers
 * a question about the numbered screens, and the count it returns is one of
 * the things the documentation is reconciled against.
 */
export function screensForRole(role: Role): ScreenDef[] {
  return SCREENS.filter((s) => s.role === role && !s.devOnly && !s.supporting)
}

export function screenById(id: string): ScreenDef | undefined {
  return SCREENS.find((s) => s.id === id)
}

export const ROLE_LABEL: Record<Role, string> = {
  customer: 'Customer',
  counter: 'Counter Staff',
  admin: 'Admin and Owner',
}

/** The catalogue, where a person goes when they sign out. */
export const CATALOGUE_PATH = '/'

/** The sign in screen, where a person goes when a screen needs an account. */
export const SIGN_IN_PATH = '/signin'

/** The registration screen, where a visitor opens an account. */
export const REGISTER_PATH = '/register'

/** The customer's own account screen. */
export const ACCOUNT_PATH = '/account'

/** The privacy notice, linked from the footer of every screen. */
export const PRIVACY_PATH = '/privacy'

/** Landing path when a role signs in. */
export const ROLE_HOME: Record<Role, string> = {
  customer: '/',
  counter: '/counter',
  admin: '/admin',
}

/**
 * Whether a path is the home of a role.
 *
 * A menu marks the item of the current screen, and an item normally counts as
 * current on every address that starts with its path, so My Hires stays marked
 * on the detail of one hire. A home is the start of every other path of its
 * area, so by that rule the counter's Today would be marked on every counter
 * screen. The menus mark a home only on its own address.
 */
export function isHomePath(path: string): boolean {
  return Object.values(ROLE_HOME).includes(path)
}
