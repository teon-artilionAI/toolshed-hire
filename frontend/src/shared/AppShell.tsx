/**
 * The frame every screen renders inside.
 *
 * Three layouts, because three people use this system in three postures. A
 * customer browses a catalogue on a phone. Counter staff stand at a trade
 * counter with a queue behind them, so their targets are generous and the
 * branch they are working at never leaves the screen. An owner reads
 * reports sitting down, so their layout is denser and visibly a different
 * tool. The layout follows the screen's own role rather than who is signed
 * in, so a counter screen always looks like a counter screen.
 */

import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import {
  AlarmClock, BarChart3, Boxes, CalendarDays, CalendarPlus, CalendarRange,
  Home, LayoutDashboard, LogOut, MapPin, MoreHorizontal, ScrollText, Search,
  ShieldCheck, ShoppingCart, Tags, User, Users, Wrench, X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Role } from './types'
import type { ScreenDef } from './navigation'
import { navForRole } from './navigation'
import { useSession } from './session'

const ICONS: Record<string, LucideIcon> = {
  AlarmClock, BarChart3, Boxes, CalendarDays, CalendarPlus, CalendarRange,
  Home, LayoutDashboard, MapPin, ScrollText, Search, ShieldCheck,
  ShoppingCart, Tags, User, Users,
}

/** Most items a phone tab bar can carry before labels stop being legible. */
const MAX_TAB_BAR_ITEMS = 5

/** One tab. 56px tall with 8px between neighbours, which is what a thumb
 *  at a counter needs. */
const TAB_CLASS =
  'flex min-h-[3.5rem] flex-1 cursor-pointer flex-col items-center justify-center gap-xs rounded px-xs py-sm text-xs leading-tight transition-colors'

/** The screen's own icon, falling back to a spanner so a new screen with
 *  no icon still renders rather than leaving a hole in the navigation. */
function NavIcon({ screen }: { screen: ScreenDef }) {
  const Icon = (screen.icon && ICONS[screen.icon]) || Wrench
  return <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
}

/** Active state is amber with ink text, which passes contrast where amber
 *  with white would not. */
function navItemClass(
  base: string,
  idle: string,
  active = 'bg-accent font-semibold text-accent-ink',
) {
  return ({ isActive }: { isActive: boolean }) =>
    `${base} ${isActive ? active : idle}`
}

function SkipLink() {
  return <a href="#main" className="skip-link">Skip to main content</a>
}

function BrandMark({ full = false }: { full?: boolean }) {
  return (
    <img
      src={full ? '/logo.png' : '/mark.png'}
      alt="Toolshed Hire"
      className={full ? 'h-9 w-auto' : 'h-8 w-8'}
    />
  )
}

/** Bottom tab bar for phones. Beyond five items the tail moves into a
 *  sheet, because six labels at 375px stop being readable. */
function MobileTabBar({ items }: { items: ScreenDef[] }) {
  const [sheetOpen, setSheetOpen] = useState(false)
  const location = useLocation()
  const overflowing = items.length > MAX_TAB_BAR_ITEMS
  const tabs = overflowing ? items.slice(0, MAX_TAB_BAR_ITEMS - 1) : items
  const rest = overflowing ? items.slice(MAX_TAB_BAR_ITEMS - 1) : []

  useEffect(() => setSheetOpen(false), [location.pathname])

  return (
    <>
      {sheetOpen && (
        <div
          id="more-nav-sheet"
          className="fixed inset-x-0 bottom-[4.5rem] z-30 border-t border-line bg-surface p-md shadow-pop md:hidden"
        >
          <div className="mb-sm flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">More</h2>
            <button type="button" className="btn px-sm text-slate-soft hover:bg-muted" onClick={() => setSheetOpen(false)}>
              <X className="h-4 w-4" aria-hidden="true" />
              <span className="sr-only">Close the more menu</span>
            </button>
          </div>
          <ul className="flex flex-col gap-sm">
            {rest.map((s) => (
              <li key={s.id}>
                <NavLink to={s.path} className={navItemClass('btn w-full justify-start', 'text-ink hover:bg-muted')}>
                  <NavIcon screen={s} />
                  {s.navLabel ?? s.name}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      )}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 flex gap-sm border-t border-line bg-surface px-sm pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {tabs.map((s) => (
          <NavLink
            key={s.id}
            to={s.path}
            end={s.path === '/'}
            className={navItemClass(TAB_CLASS, 'text-slate-soft hover:bg-muted', 'bg-accent-wash font-semibold text-ink')}
          >
            <NavIcon screen={s} />
            <span className="text-center">{s.navLabel ?? s.name}</span>
          </NavLink>
        ))}
        {overflowing && (
          <button
            type="button"
            aria-expanded={sheetOpen}
            aria-controls="more-nav-sheet"
            onClick={() => setSheetOpen((v) => !v)}
            className={`${TAB_CLASS} text-slate-soft hover:bg-muted`}
          >
            <MoreHorizontal className="h-5 w-5 shrink-0" aria-hidden="true" />
            <span>More</span>
          </button>
        )}
      </nav>
    </>
  )
}

/** Who you are, and the way out. Shared by both staff sidebars. */
function AuthControl({ signOutClass }: { signOutClass: string }) {
  const { signedIn, user, signOut } = useSession()
  if (!signedIn || !user) {
    return <Link to="/signin" className="btn-primary w-full">Sign in</Link>
  }
  return (
    <>
      <p className="truncate text-sm font-medium">{user.name}</p>
      <button type="button" onClick={signOut} className={`btn mt-sm w-full justify-start px-sm ${signOutClass}`}>
        <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
        Sign out
      </button>
    </>
  )
}

interface StaffChrome {
  heading: string
  subheading: string
  dark?: boolean
}

/** Who the staff member is and where they are standing. */
function Whereabouts({ heading, subheading, dark = false }: StaffChrome) {
  return (
    <>
      <BrandMark />
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold">{heading}</p>
        <p className={`truncate text-xs ${dark ? 'text-slate-dim' : 'text-slate-soft'}`}>{subheading}</p>
      </div>
    </>
  )
}

/** Desktop side navigation for staff. `dark` is the owner's tool, which is
 *  deliberately a different object from the counter's. */
function Sidebar({ items, heading, subheading, dark = false }: StaffChrome & { items: ScreenDef[] }) {
  const ground = dark ? 'bg-slate text-white border-slate-soft' : 'bg-surface text-ink border-line'
  const edge = dark ? 'border-slate-soft' : 'border-line'
  const idle = dark ? 'text-white hover:bg-slate-soft' : 'text-slate hover:bg-muted hover:text-ink'
  const size = dark ? 'min-h-[2.75rem] text-sm' : 'min-h-[3rem] text-base'

  return (
    <aside className={`hidden w-64 shrink-0 flex-col border-r md:flex ${ground}`}>
      <div className={`flex items-center gap-sm border-b p-md ${edge}`}>
        <Whereabouts heading={heading} subheading={subheading} dark={dark} />
      </div>
      <nav aria-label="Primary" className="flex-1 overflow-y-auto p-sm">
        <ul className="flex flex-col gap-sm">
          {items.map((s) => (
            <li key={s.id}>
              <NavLink
                to={s.path}
                className={navItemClass(`flex cursor-pointer items-center gap-sm rounded px-md py-sm transition-colors ${size}`, idle)}
              >
                <NavIcon screen={s} />
                <span className="truncate">{s.navLabel ?? s.name}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className={`border-t p-md ${edge}`}>
        <AuthControl signOutClass={idle} />
      </div>
    </aside>
  )
}

function CustomerHeader({ items }: { items: ScreenDef[] }) {
  const { signedIn, user, basketCount, signOut } = useSession()
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-md px-md py-sm">
        {/* The logo is 36px tall, so the link gets its own 44px minimum
            rather than inheriting the image's height as its target. */}
        <Link
          to="/"
          className="flex min-h-[2.75rem] min-w-[2.75rem] shrink-0 cursor-pointer items-center"
          aria-label="Toolshed Hire, home"
        >
          <BrandMark full />
        </Link>
        <nav aria-label="Primary" className="hidden flex-1 md:block">
          <ul className="flex items-center gap-sm">
            {items.map((s) => (
              <li key={s.id}>
                <NavLink
                  to={s.path}
                  end={s.path === '/'}
                  className={navItemClass('btn px-md', 'text-slate hover:bg-muted hover:text-ink', 'bg-accent-wash font-semibold text-ink')}
                >
                  {s.navLabel ?? s.name}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="ml-auto flex items-center gap-sm">
          <Link
            to="/basket"
            className="btn hidden px-sm text-slate hover:bg-muted hover:text-ink md:inline-flex"
            aria-label={`Basket, ${basketCount} ${basketCount === 1 ? 'item' : 'items'}`}
          >
            <ShoppingCart className="h-5 w-5 shrink-0" aria-hidden="true" />
            <span className="tabular text-sm font-semibold">{basketCount}</span>
          </Link>
          {signedIn && user ? (
            <button type="button" onClick={signOut} className="btn-secondary px-md text-sm">
              <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="hidden sm:inline">Sign out</span>
              <span className="sr-only sm:hidden">Sign out</span>
            </button>
          ) : (
            <Link to="/signin" className="btn-primary px-md text-sm">Sign in</Link>
          )}
        </div>
      </div>
    </header>
  )
}

const MAIN_CLASS =
  'mx-auto w-full max-w-6xl flex-1 px-md py-lg pb-[8.5rem] md:pb-2xl'

/** @param variant which layout to draw, taken from the screen's own role. */
export default function AppShell({ variant, children }: { variant: Role; children: ReactNode }) {
  const { branch } = useSession()
  const items = navForRole(variant)

  if (variant === 'customer') {
    return (
      <div className="flex min-h-dvh flex-col">
        <SkipLink />
        <CustomerHeader items={items} />
        <main id="main" className={MAIN_CLASS}>{children}</main>
        <MobileTabBar items={items.slice(0, MAX_TAB_BAR_ITEMS)} />
      </div>
    )
  }

  const isAdmin = variant === 'admin'
  const heading = isAdmin ? 'Toolshed Hire' : branch.name
  const subheading = isAdmin ? 'Owner and admin' : `${branch.suburb} branch counter`

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      <SkipLink />
      <Sidebar items={items} heading={heading} subheading={subheading} dark={isAdmin} />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-sm border-b border-line bg-surface px-md py-sm md:hidden">
          <Whereabouts heading={heading} subheading={subheading} />
        </div>
        {!isAdmin && (
          <p className="sr-only" aria-live="polite">Working at the {branch.name} branch</p>
        )}
        <main id="main" className={MAIN_CLASS}>{children}</main>
      </div>
      <MobileTabBar items={items} />
    </div>
  )
}
