/**
 * Tests for the rules that read the screen inventory.
 *
 * Who may open a screen, what each menu offers, and where a person lands after
 * signing in. The inventory itself is the input, so a screen added with the
 * wrong flag fails here.
 */

import { describe, expect, it } from 'vitest'
import { SCREENS, screenById } from './navigation'
import type { ScreenDef } from './navigation'
import {
  accessTo,
  landingFor,
  navFor,
  screenForPath,
  signInAddress,
} from './screen-access'
import type { Role } from './types'

function screen(id: string): ScreenDef {
  const found = screenById(id)
  if (!found) throw new Error(`The inventory has no screen ${id}.`)
  return found
}

const ROLES: Role[] = ['customer', 'counter', 'admin']

describe('who may open a screen', () => {
  it('lets anybody open a public screen, signed in or not', () => {
    for (const publicScreen of SCREENS.filter((candidate) => candidate.publicAccess)) {
      expect(accessTo(publicScreen, null)).toBe('allowed')
      for (const role of ROLES) expect(accessTo(publicScreen, role)).toBe('allowed')
    }
  })

  it('sends a signed out person to sign in for every protected screen', () => {
    const guarded = SCREENS.filter((candidate) => !candidate.publicAccess)

    expect(guarded.length).toBeGreaterThan(0)
    for (const guardedScreen of guarded) {
      expect(accessTo(guardedScreen, null)).toBe('signInNeeded')
    }
  })

  it.each([
    ['customer', 'SC-07', 'allowed'],
    ['customer', 'SC-10', 'wrongRole'],
    ['customer', 'SC-19', 'wrongRole'],
    ['counter', 'SC-10', 'allowed'],
    ['counter', 'SC-14', 'allowed'],
    ['counter', 'SC-07', 'wrongRole'],
    ['counter', 'SC-19', 'wrongRole'],
    ['admin', 'SC-19', 'allowed'],
    ['admin', 'SC-10', 'allowed'],
    ['admin', 'SC-18', 'allowed'],
    ['admin', 'SC-07', 'wrongRole'],
  ] as const)('answers a %s account asking for %s with %s', (role, id, expected) => {
    expect(accessTo(screen(id), role)).toBe(expected)
  })

  it('keeps the screens that were public before public, with the privacy notice, and no others', () => {
    const publicIds = SCREENS.filter((candidate) => candidate.publicAccess).map(
      (candidate) => candidate.id,
    )

    expect(publicIds).toEqual([
      'SC-01',
      'SC-02',
      'SC-03',
      'SC-04',
      'SC-05',
      'SC-06',
      'INFO-01',
      'DEV-01',
    ])
  })
})

describe('the screen an address belongs to', () => {
  it.each([
    ['/', 'SC-01'],
    ['/model/cp-100-plate-compactor', 'SC-03'],
    ['/reservations/TSH-R-26-000123', 'SC-08'],
    ['/counter', 'SC-10'],
    ['/counter/checkout/rn-1', 'SC-14'],
    ['/admin/users', 'SC-23'],
    ['/privacy', 'INFO-01'],
  ])('finds %s as %s', (path, id) => {
    expect(screenForPath(path)?.id).toBe(id)
  })

  it('finds nothing for an address no screen has', () => {
    expect(screenForPath('/nowhere')).toBeUndefined()
    expect(screenForPath('/counter/nowhere/at/all')).toBeUndefined()
  })
})

describe('the menu', () => {
  it('offers a visitor and a customer the customer screens only', () => {
    const visitor = navFor(null)

    expect(visitor).toEqual(navFor('customer'))
    expect(visitor.every((item) => item.role === 'customer')).toBe(true)
    expect(visitor.map((item) => item.navLabel)).toEqual([
      'Catalogue',
      'Search',
      'Basket',
      'My Hires',
      'Account',
    ])
  })

  it('offers counter staff the counter screens only', () => {
    const menu = navFor('counter')

    expect(menu.length).toBeGreaterThan(0)
    expect(menu.every((item) => item.role === 'counter')).toBe(true)
  })

  it('offers an admin the admin screens and then the counter screens', () => {
    const areas = navFor('admin').map((item) => item.role)

    expect(new Set(areas)).toEqual(new Set(['admin', 'counter']))
    expect(areas.lastIndexOf('admin')).toBeLessThan(areas.indexOf('counter'))
  })

  it('never offers the development screen or a supporting page', () => {
    for (const role of [null, ...ROLES]) {
      expect(navFor(role).some((item) => item.devOnly || item.supporting)).toBe(false)
    }
  })
})

describe('where a person lands after signing in', () => {
  it('is the home of their role when they were going nowhere in particular', () => {
    expect(landingFor('customer', null)).toBe('/')
    expect(landingFor('counter', null)).toBe('/counter')
    expect(landingFor('admin', null)).toBe('/admin')
  })

  it('is the screen they were trying to reach, query string and all', () => {
    expect(landingFor('customer', '/reservations/TSH-R-26-000123')).toBe(
      '/reservations/TSH-R-26-000123',
    )
    expect(landingFor('counter', '/counter/diary')).toBe('/counter/diary')
    expect(landingFor('admin', '/counter/overdue')).toBe('/counter/overdue')
    expect(landingFor('customer', '/search?from=2026-03-12&to=2026-03-16')).toBe(
      '/search?from=2026-03-12&to=2026-03-16',
    )
  })

  it('is their own home when the screen they wanted is not for their role', () => {
    expect(landingFor('customer', '/counter')).toBe('/')
    expect(landingFor('counter', '/admin/users')).toBe('/counter')
  })

  it.each([
    'https://example.com/steal',
    '//example.com/steal',
    '/\\example.com',
    'javascript:alert(1)',
    '/not-a-screen',
    '/signin',
    '',
  ])('never follows %j, which is not a screen of this application', (next) => {
    expect(landingFor('customer', next)).toBe('/')
  })

  it('writes the address a person was on into the sign in address', () => {
    expect(signInAddress('/counter/diary')).toBe('/signin?next=%2Fcounter%2Fdiary')
    expect(signInAddress('/search?from=2026-03-12')).toBe(
      '/signin?next=%2Fsearch%3Ffrom%3D2026-03-12',
    )
  })
})
