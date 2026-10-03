/**
 * The frame every screen renders inside.
 *
 * Three layouts, because three people use this system in three postures. A
 * customer browses a catalogue on a phone. Counter staff stand at a trade
 * counter with a queue behind them, so their targets are generous and the
 * branch they work at never leaves the screen. An owner reads reports sitting
 * down, so their layout is denser and visibly a different tool.
 *
 * The layout and the menu follow the person who is signed in. A visitor and a
 * customer get the customer layout. Counter staff get the counter layout with
 * the name of their branch, which comes from their account. An admin gets the
 * owner's layout, with the counter screens in the same menu because an admin
 * may use those too. The rule for the menu is `navFor` in screen-access.ts.
 *
 * The shell also owns the notice that says a screen still shows sample data,
 * and the footer under every screen, which links to the privacy notice.
 *
 * The count beside the basket in the customer header is how many units the
 * hire basket holds. It comes from the basket itself, in basket-store.ts, so
 * it is right on every screen and after a reload.
 */

import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LogOut, ShoppingCart } from 'lucide-react'
import { catalogueQueries } from './api/catalogue-queries'
import { basketUnitCount } from './basket-store'
import type { ScreenDef } from './navigation'
import { CATALOGUE_PATH, PRIVACY_PATH, SIGN_IN_PATH, isHomePath } from './navigation'
import { SampleDataNotice } from './sample-data-notice'
import { navFor } from './screen-access'
import { BrandMark, MobileTabBar, NavIcon, SkipLink } from './shell-nav'
import { MAX_TAB_BAR_ITEMS, navItemClass } from './shell-nav-style'
import { useBasket } from './use-basket'
import { useSession } from './use-session'

/** Who you are, and the way out. Shared by both staff sidebars. */
function AuthControl({ signOutClass }: { signOutClass: string }) {
  const { user, signOut, signingOut } = useSession()
  if (!user) {
    return <Link to={SIGN_IN_PATH} className="btn-primary w-full">Sign in</Link>
  }
  return (
    <>
      <p className="truncate text-sm font-medium">{user.fullName}</p>
      <button
        type="button"
        onClick={signOut}
        disabled={signingOut}
        className={`btn mt-sm w-full justify-start px-sm ${signOutClass}`}
      >
        <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
        Sign out
      </button>
    </>
  )
}

/** The way out on a phone, where the staff sidebar is not shown. */
function MobileSignOut() {
  const { signOut, signingOut } = useSession()
  return (
    <button type="button" onClick={signOut} disabled={signingOut} className="btn-secondary px-sm text-sm">
      <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="sr-only">Sign out</span>
    </button>
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
 *  deliberately a different object from the counter's. It stays in view while
 *  the screen scrolls, so the way out is never below a long page. */
function Sidebar({ items, heading, subheading, dark = false }: StaffChrome & { items: ScreenDef[] }) {
  const ground = dark ? 'bg-slate text-white border-slate-soft' : 'bg-surface text-ink border-line'
  const edge = dark ? 'border-slate-soft' : 'border-line'
  const idle = dark ? 'text-white hover:bg-slate-soft' : 'text-slate hover:bg-muted hover:text-ink'
  const size = dark ? 'min-h-[2.75rem] text-sm' : 'min-h-[3rem] text-base'

  return (
    <aside className={`hidden w-64 shrink-0 flex-col border-r md:sticky md:top-0 md:flex md:h-dvh ${ground}`}>
      <div className={`flex items-center gap-sm border-b p-md ${edge}`}>
        <Whereabouts heading={heading} subheading={subheading} dark={dark} />
      </div>
      <nav aria-label="Primary" className="flex-1 overflow-y-auto p-sm">
        <ul className="flex flex-col gap-sm">
          {items.map((s) => (
            <li key={s.id}>
              <NavLink
                to={s.path}
                end={isHomePath(s.path)}
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
  const { user, signOut, signingOut } = useSession()
  const basketCount = basketUnitCount(useBasket())
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-md px-md py-sm">
        {/* The logo is 36px tall, so the link gets its own 44px minimum
            rather than inheriting the image's height as its target. */}
        <Link
          to={CATALOGUE_PATH}
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
                  end={isHomePath(s.path)}
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
          {user ? (
            <button
              type="button"
              onClick={signOut}
              disabled={signingOut}
              className="btn-secondary px-md text-sm"
            >
              <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="hidden sm:inline">Sign out</span>
              <span className="sr-only sm:hidden">Sign out</span>
            </button>
          ) : (
            <Link to={SIGN_IN_PATH} className="btn-primary px-md text-sm">Sign in</Link>
          )}
        </div>
      </div>
    </header>
  )
}

/**
 * The name of the branch a counter account works at.
 *
 * The account carries the branch code and the API knows the name. Until the
 * list of branches has arrived, and if it cannot be loaded, the code stands in
 * for the name, so the counter layout always says where the person is.
 */
function useCounterBranch(branchCode: string | null): StaffChrome {
  const branches = useQuery({ ...catalogueQueries.branches(), enabled: branchCode !== null })
  if (branchCode === null) return { heading: 'Toolshed Hire', subheading: 'Branch counter' }
  const branch = branches.data?.items.find((candidate) => candidate.code === branchCode)
  return branch
    ? { heading: branch.name, subheading: `${branch.suburb} branch counter` }
    : { heading: `Branch ${branchCode}`, subheading: 'Branch counter' }
}

/** `tabIndex` lets the router move focus here when the address changes, and
 *  lets the skip link land on it. It is not a tab stop. */
function Main({ screen, children }: { screen?: ScreenDef; children: ReactNode }) {
  return (
    <main
      id="main"
      tabIndex={-1}
      className="mx-auto w-full max-w-6xl flex-1 px-md py-lg"
    >
      <SampleDataNotice screen={screen} />
      {children}
    </main>
  )
}

/**
 * The footer under every screen, in all three layouts.
 *
 * On a phone the tab bar is fixed to the bottom of the window, so the footer
 * keeps clear of it with padding of its own. The link is a full 44 pixel
 * target.
 */
function ShellFooter() {
  return (
    <footer className="mx-auto w-full max-w-6xl px-md pb-[6.5rem] md:pb-lg">
      <div className="flex flex-wrap items-center justify-between gap-x-md border-t border-line pt-sm text-sm text-slate-soft">
        <p>Toolshed Hire</p>
        <Link
          to={PRIVACY_PATH}
          className="inline-flex min-h-[2.75rem] cursor-pointer items-center font-medium text-ink underline transition-colors duration-200 hover:text-slate"
        >
          Privacy notice
        </Link>
      </div>
    </footer>
  )
}

/**
 * @param screen The screen being shown. Leave it out when the shell frames
 *   something that is not a screen, such as a refusal or a missing page, so
 *   the sample data notice is not shown above it.
 */
export default function AppShell({ screen, children }: { screen?: ScreenDef; children: ReactNode }) {
  const { user, role } = useSession()
  const items = navFor(role)
  const counter = useCounterBranch(role === 'counter' ? (user?.branchCode ?? null) : null)

  if (role === null || role === 'customer') {
    return (
      <div className="flex min-h-dvh flex-col">
        <SkipLink />
        <CustomerHeader items={items} />
        <Main screen={screen}>{children}</Main>
        <ShellFooter />
        <MobileTabBar items={items.slice(0, MAX_TAB_BAR_ITEMS)} />
      </div>
    )
  }

  const isAdmin = role === 'admin'
  const chrome: StaffChrome = isAdmin
    ? { heading: 'Toolshed Hire', subheading: 'Owner and admin' }
    : counter

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      <SkipLink />
      <Sidebar items={items} {...chrome} dark={isAdmin} />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-sm border-b border-line bg-surface px-md py-sm md:hidden">
          <Whereabouts {...chrome} />
          {/* A phone has no sidebar, so the way out sits beside the branch. */}
          <div className="ml-auto shrink-0">
            <MobileSignOut />
          </div>
        </div>
        {!isAdmin && (
          <p className="sr-only" aria-live="polite">Working at {chrome.heading}</p>
        )}
        <Main screen={screen}>{children}</Main>
        <ShellFooter />
      </div>
      <MobileTabBar items={items} />
    </div>
  )
}
