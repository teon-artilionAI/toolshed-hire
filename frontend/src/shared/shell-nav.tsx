/**
 * The navigation pieces every layout of the shell is built from.
 *
 * The skip link, the brand mark, the icon of a screen and the phone tab bar.
 * They are the same in all three layouts, so they live here and the shell
 * only arranges them.
 */

import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  AlarmClock, BarChart3, Boxes, CalendarDays, CalendarPlus, CalendarRange,
  Home, LayoutDashboard, MapPin, MoreHorizontal, ScrollText, Search,
  ShieldCheck, ShoppingCart, Tags, User, Users, Wrench, X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { isHomePath } from './navigation'
import type { ScreenDef } from './navigation'
import { MAX_TAB_BAR_ITEMS, TAB_CLASS, navItemClass } from './shell-nav-style'

const ICONS: Record<string, LucideIcon> = {
  AlarmClock, BarChart3, Boxes, CalendarDays, CalendarPlus, CalendarRange,
  Home, LayoutDashboard, MapPin, ScrollText, Search, ShieldCheck,
  ShoppingCart, Tags, User, Users,
}

/** The screen's own icon, falling back to a spanner so a new screen with
 *  no icon still renders rather than leaving a hole in the navigation. */
export function NavIcon({ screen }: { screen: ScreenDef }) {
  const Icon = (screen.icon && ICONS[screen.icon]) || Wrench
  return <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
}

export function SkipLink() {
  return <a href="#main" className="skip-link">Skip to main content</a>
}

export function BrandMark({ full = false }: { full?: boolean }) {
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
export function MobileTabBar({ items }: { items: ScreenDef[] }) {
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
                <NavLink to={s.path} end={isHomePath(s.path)} className={navItemClass('btn w-full justify-start', 'text-ink hover:bg-muted')}>
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
            end={isHomePath(s.path)}
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
