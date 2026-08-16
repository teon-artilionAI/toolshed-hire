/**
 * Who is using the prototype right now.
 *
 * The prototype has no back end and no authentication, which Task 1
 * permits. What it does need is a single honest answer to three questions
 * that almost every screen asks: which role is looking at this, who are
 * they, and which branch are they standing in. That answer lives here so
 * that no screen has to invent its own.
 *
 * The role switcher at the bottom of the window exists because a marker
 * assessing three role based flows will not be issued three sets of
 * credentials. It is deliberately styled as a demonstration control and
 * labelled as one, so it can never be mistaken for part of the product.
 */

import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Check, FlaskConical, X } from 'lucide-react'
import type { Branch, BranchCode, Role, UserAccount } from './types'
import { branches, users } from './fixtures'
import { ROLE_LABEL } from './navigation'

/** The fixture account each role signs in as during a demonstration. */
const DEMO_ACCOUNT_EMAIL: Record<Role, string> = {
  customer: 'w.adonis@buildright.co.za',
  counter: 'elmarie@toolshedhire.co.za',
  admin: 'marius@toolshedhire.co.za',
}

const DEFAULT_BRANCH_CODE: BranchCode = 'CBD'
const ROLE_ORDER: Role[] = ['customer', 'counter', 'admin']

function demoAccountFor(role: Role): UserAccount {
  const account = users.find((u) => u.email === DEMO_ACCOUNT_EMAIL[role])
  if (!account) {
    throw new Error(
      `No fixture account for the ${role} role (looked for ${DEMO_ACCOUNT_EMAIL[role]}). ` +
        'Add the account to fixtures.users or correct DEMO_ACCOUNT_EMAIL in session.tsx.',
    )
  }
  return account
}

function branchFor(code: BranchCode): Branch {
  const branch = branches.find((b) => b.code === code)
  if (!branch) {
    throw new Error(
      `Unknown branch code "${code}". Valid codes come from fixtures.branches.`,
    )
  }
  return branch
}

export interface Session {
  /** The role the interface should behave as. Signed out means customer. */
  role: Role
  signedIn: boolean
  /** The signed in account, or null when signed out. */
  user: UserAccount | null
  /** The branch counter staff are working at. Never null, so the counter
   *  layout can always show where you are standing. */
  branch: Branch
  /** Items in the hire basket. The basket screen owns the contents; the
   *  shell only needs the count for its indicator. */
  basketCount: number
  signInAs: (role: Role) => void
  signOut: () => void
  setBranchCode: (code: BranchCode) => void
  setBasketCount: (count: number) => void
}

const SessionContext = createContext<Session | undefined>(undefined)

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) {
    throw new Error(
      'useSession was called outside SessionProvider. Wrap the router in <SessionProvider> in App.tsx.',
    )
  }
  return session
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserAccount | null>(null)
  const [branchCode, setBranchCodeState] = useState<BranchCode>(DEFAULT_BRANCH_CODE)
  const [basketCount, setBasketCount] = useState(0)

  const signInAs = useCallback((role: Role) => {
    const account = demoAccountFor(role)
    setUser(account)
    if (account.branchCode) setBranchCodeState(account.branchCode)
  }, [])

  const signOut = useCallback(() => setUser(null), [])

  const value = useMemo<Session>(
    () => ({
      role: user?.role ?? 'customer',
      signedIn: user !== null,
      user,
      branch: branchFor(branchCode),
      basketCount,
      signInAs,
      signOut,
      setBranchCode: setBranchCodeState,
      setBasketCount,
    }),
    [user, branchCode, basketCount, signInAs, signOut],
  )

  return (
    <SessionContext.Provider value={value}>
      {children}
      <RoleSwitcher />
    </SessionContext.Provider>
  )
}

/**
 * Demonstration control. Sits clear of the mobile bottom bar so it never
 * covers navigation, collapses to a single button, and is reachable by
 * keyboard like anything else.
 */
function RoleSwitcher() {
  const { role, signedIn, user, branch, signInAs, signOut, setBranchCode } =
    useSession()
  const [open, setOpen] = useState(false)

  return (
    <div
      /* Marked so screenshot capture can hide it. A fixed element renders
         at its viewport position inside a full page capture, which lands it
         in the middle of the content and reads as a defect in a document. */
      data-demo-control="true"
      className="fixed bottom-[5.75rem] right-md z-40 md:bottom-md"
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
      }}
    >
      {open ? (
        <div
          id="demo-role-switcher"
          role="group"
          aria-label="Prototype demonstration controls"
          className="w-[min(19rem,calc(100vw-2rem))] rounded-lg border-2 border-dashed border-slate-dim bg-ink p-md text-white shadow-pop"
        >
          <div className="mb-sm flex items-start justify-between gap-sm">
            <div className="min-w-0">
              <p className="font-mono text-xs uppercase tracking-wide text-accent">
                Demo control
              </p>
              <p className="mt-xs text-xs text-slate-dim">
                Switches role so all three flows can be shown. Not part of the
                product.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="btn -mr-sm -mt-sm shrink-0 px-sm text-white hover:bg-slate"
            >
              <X className="h-4 w-4" aria-hidden="true" />
              <span className="sr-only">Close demonstration controls</span>
            </button>
          </div>

          <ul className="flex flex-col gap-sm">
            {ROLE_ORDER.map((r) => {
              const current = signedIn && role === r
              return (
                <li key={r}>
                  <button
                    type="button"
                    aria-pressed={current}
                    onClick={() => signInAs(r)}
                    className={`btn w-full justify-start ${
                      current
                        ? 'bg-white font-semibold text-ink'
                        : 'bg-slate text-white hover:bg-slate-soft'
                    }`}
                  >
                    {current ? (
                      <Check className="h-4 w-4 shrink-0" aria-hidden="true" />
                    ) : (
                      <FlaskConical
                        className="h-4 w-4 shrink-0"
                        aria-hidden="true"
                      />
                    )}
                    <span className="truncate">
                      {ROLE_LABEL[r]}
                      {current ? ' (signed in)' : ''}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>

          {signedIn && role === 'counter' && (
            <div className="mt-md">
              <label className="field-label text-white" htmlFor="demo-branch">
                Working at
              </label>
              <select
                id="demo-branch"
                className="field-input bg-slate text-white"
                value={branch.code}
                onChange={(e) => setBranchCode(e.target.value as BranchCode)}
              >
                {branches.map((b) => (
                  <option key={b.code} value={b.code}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="mt-md flex items-center justify-between gap-sm border-t border-slate pt-sm">
            <p className="min-w-0 truncate text-xs text-slate-dim">
              {signedIn && user ? user.name : 'Signed out, browsing as a visitor'}
            </p>
            {signedIn && (
              <button
                type="button"
                onClick={signOut}
                className="btn shrink-0 px-sm text-xs text-white underline hover:bg-slate"
              >
                Sign out
              </button>
            )}
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-expanded={false}
          aria-controls="demo-role-switcher"
          className="btn border-2 border-dashed border-slate-dim bg-ink text-white shadow-pop hover:bg-slate"
        >
          <FlaskConical className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="truncate">
            Demo: {signedIn ? ROLE_LABEL[role] : 'Signed out'}
          </span>
        </button>
      )}
    </div>
  )
}
