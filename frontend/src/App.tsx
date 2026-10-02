/**
 * The router.
 *
 * Every screen in the documented inventory gets an address here, from the
 * first commit, whether or not its module exists yet. That is deliberate.
 * The prototype, the journey map and the built system have to reconcile with
 * one another, and a screen that is reachable in one and missing from another
 * is a finding.
 *
 * Screen modules load lazily, one chunk each, so the first paint carries
 * only the screen being looked at. All twenty four are present; an id with
 * no module falls back to the placeholder rather than a blank page, which
 * is what a newly added inventory entry looks like before its screen lands.
 *
 * DEV-01 is routed from the same table and is not one of the twenty four. It
 * is the connectivity panel at /system. Keeping it in this table rather than
 * adding a second routing mechanism beside it is the whole reason the table
 * exists.
 *
 * Every screen renders inside an error boundary. A screen that throws shows the
 * shared error state in its place, and the shell and its navigation stay up.
 *
 * THE GUARD
 * =========
 * Every route passes through `ScreenRoute`, which asks screen-access.ts whether
 * the person may open the screen. The answer comes from `publicAccess` and
 * `role` in the inventory. A signed out person who opens a protected screen is
 * sent to sign in, with the address they wanted in the query string so they
 * are brought back afterwards. A signed in person whose role does not reach
 * the screen is told so and offered their own home. The screen module is never
 * rendered in either case.
 */

import { Suspense, lazy, useEffect, useRef } from 'react'
import type { ComponentType } from 'react'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { CATALOGUE_PATH, SCREENS, ROLE_HOME, ROLE_LABEL } from './shared/navigation'
import type { ScreenDef } from './shared/navigation'
import AppShell from './shared/AppShell'
import { ScreenErrorBoundary } from './shared/error-boundary'
import { NoAccess } from './shared/no-access'
import { accessTo, signInAddress } from './shared/screen-access'
import { SessionProvider } from './shared/session'
import { PageHeader } from './shared/ui'
import { useSession } from './shared/use-session'
import Placeholder from './features/placeholder'

type ScreenLoader = () => Promise<{ default: ComponentType }>

/**
 * Where each screen's module lives. One entry per id in the inventory,
 * written as a literal dynamic import so the bundler can split each screen
 * into its own chunk and so a missing file is a build error rather than a
 * silent blank page.
 */
const SCREEN_MODULE: Record<string, ScreenLoader> = {
  'SC-01': () => import('./features/customer/SC01-Catalogue-Home'),
  'SC-02': () => import('./features/customer/SC02-Availability-Search-Results'),
  'SC-03': () => import('./features/customer/SC03-Product-Model-Detail'),
  'SC-04': () => import('./features/customer/SC04-Hire-Basket-And-Booking-Review'),
  'SC-05': () => import('./features/customer/SC05-Register'),
  'SC-06': () => import('./features/customer/SC06-Sign-In'),
  'SC-07': () => import('./features/customer/SC07-My-Reservations'),
  'SC-08': () => import('./features/customer/SC08-Reservation-Detail'),
  'SC-09': () => import('./features/customer/SC09-My-Account'),
  'SC-10': () => import('./features/counter/SC10-Counter-Dashboard'),
  'SC-11': () => import('./features/counter/SC11-Branch-Diary'),
  'SC-12': () => import('./features/counter/SC12-Customer-Lookup'),
  'SC-13': () => import('./features/counter/SC13-New-Booking'),
  'SC-14': () => import('./features/counter/SC14-Checkout-Deposit'),
  'SC-15': () => import('./features/counter/SC15-Return-Inspection'),
  'SC-16': () => import('./features/counter/SC16-Damage-Capture'),
  'SC-17': () => import('./features/counter/SC17-Asset-Locator'),
  'SC-18': () => import('./features/counter/SC18-Overdue-Worklist'),
  'SC-19': () => import('./features/admin/SC19-Admin-Dashboard'),
  'SC-20': () => import('./features/admin/SC20-Catalogue-Pricing'),
  'SC-21': () => import('./features/admin/SC21-Asset-Register'),
  'SC-22': () => import('./features/admin/SC22-Utilisation-Report'),
  'SC-23': () => import('./features/admin/SC23-User-Management'),
  'SC-24': () => import('./features/admin/SC24-Audit-Log'),
  'DEV-01': () => import('./features/system/SystemStatus'),
}

function loaderFor(screen: ScreenDef): ScreenLoader {
  const load = SCREEN_MODULE[screen.id]
  if (!load) {
    return () =>
      Promise.resolve({ default: () => <Placeholder screen={screen} /> })
  }
  return load
}

const ROUTES = SCREENS.map((screen) => ({
  screen,
  Screen: lazy(loaderFor(screen)),
}))

/** A skeleton rather than a spinner, so the page does not jump when the
 *  real content arrives. */
function ScreenSkeleton() {
  return (
    <div>
      <p role="status" className="sr-only">
        Loading
      </p>
      <div className="animate-pulse" aria-hidden="true">
        <div className="mb-xs h-3 w-16 rounded bg-muted" />
        <div className="mb-lg h-8 w-2/3 max-w-sm rounded bg-muted" />
        <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-28 rounded-lg border border-line bg-surface" />
          ))}
        </div>
        <div className="rounded-lg border border-line bg-surface">
          <div className="h-10 rounded-t-lg bg-muted" />
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="border-t border-line px-md py-md">
              <div className="h-4 w-full max-w-lg rounded bg-muted" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const NO_ACCESS_TITLE = 'No access'

function ScreenRoute({
  screen,
  Screen,
}: {
  screen: ScreenDef
  Screen: ComponentType
}) {
  const { pathname, search } = useLocation()
  const { role } = useSession()
  const access = accessTo(screen, role)
  useEffect(() => {
    document.title = `${access === 'wrongRole' ? NO_ACCESS_TITLE : screen.name} | Toolshed Hire`
  }, [screen, access])

  if (access === 'signInNeeded') {
    return <Navigate to={signInAddress(`${pathname}${search}`)} replace />
  }
  if (access === 'wrongRole') {
    return (
      <AppShell>
        <NoAccess screen={screen} />
      </AppShell>
    )
  }

  return (
    <AppShell screen={screen}>
      {/* Keyed by the path, so a failure on one address is gone on the next.
          The query string is left out on purpose. A search that changes its
          filters must not lose its place. */}
      <ScreenErrorBoundary key={pathname}>
        <Suspense fallback={<ScreenSkeleton />}>
          <Screen />
        </Suspense>
      </ScreenErrorBoundary>
    </AppShell>
  )
}

function NotFound() {
  const { role } = useSession()
  useEffect(() => {
    document.title = 'Page not found | Toolshed Hire'
  }, [])

  return (
    <AppShell>
      <PageHeader
        title="We cannot find that page"
        subtitle="The address may have been mistyped, or the page may have moved. Nothing has been lost."
      />
      <div className="card p-lg">
        <p className="text-sm text-slate-soft">
          Go back to the {role ? `${ROLE_LABEL[role].toLowerCase()} home screen` : 'catalogue'} and
          carry on from there.
        </p>
        <Link to={role ? ROLE_HOME[role] : CATALOGUE_PATH} className="btn-primary mt-md px-md">
          Take me home
        </Link>
      </div>
    </AppShell>
  )
}

/** The id of the main region in AppShell, which the skip link also targets. */
const MAIN_REGION_ID = 'main'

/**
 * Moves keyboard focus to the main region when the address changes.
 *
 * Without this, focus stays on the link or button that caused the move, which
 * may no longer be on the page. After a sign in or a redirect a keyboard or
 * screen reader user would be left at the top of the document, or nowhere.
 * The first address is left alone, so a page load starts where a browser
 * normally starts it.
 */
function RouteFocus() {
  const { pathname } = useLocation()
  const previous = useRef(pathname)
  useEffect(() => {
    if (previous.current === pathname) return
    previous.current = pathname
    document.getElementById(MAIN_REGION_ID)?.focus({ preventScroll: true })
  }, [pathname])
  return null
}

export default function App() {
  return (
    <SessionProvider>
      <RouteFocus />
      <Routes>
        {ROUTES.map(({ screen, Screen }) => (
          <Route
            key={screen.id}
            path={screen.path}
            element={<ScreenRoute screen={screen} Screen={Screen} />}
          />
        ))}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </SessionProvider>
  )
}
