/**
 * SC-23, User and role management.
 *
 * Two jobs on one screen because they are the same job, deciding who may do
 * what. Staff accounts carry a role and, for counter staff, a branch, and can
 * be deactivated and reactivated. Customers can be put on hold or blacklisted
 * and released again without losing their history.
 *
 * Both are read from the API one page at a time. The view on the screen, its
 * filters and its page are in the address, read and written by
 * users-address.ts, so a reload or a shared link opens the same page. The
 * views are two links, each marked as the current page when it is, and moving
 * from one to the other moves focus to the heading of the new one.
 *
 * The rules that refuse are the server's. It will not deactivate or demote the
 * last active administrator, and it will not let an administrator deactivate
 * their own account, because either would lock everybody out of this very
 * screen. The browser does not guess at either. It asks, and shows the
 * server's sentence. No password is ever shown or asked for here. A new member
 * of staff chooses their own from a link.
 */

import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ShieldCheck, Users } from 'lucide-react'
import { PageHeader } from '../../shared/ui'
import { USERS_PATH } from './admin-links'
import CustomerHolds from './SC23-Customer-Holds'
import StaffAccounts from './SC23-Staff-Accounts'
import { readView, usersViewHref } from './users-address'
import type { UsersView } from './users-address'

const VIEW_HEADING: Record<UsersView, string> = {
  staff: 'Staff accounts',
  customers: 'Customer holds',
}

const VIEW_HEADING_ID = 'users-view-heading'

function ViewLink({ view, current, children }: { view: UsersView; current: UsersView; children: ReactNode }) {
  const here = view === current
  return (
    <Link
      to={usersViewHref(USERS_PATH, view)}
      aria-current={here ? 'page' : undefined}
      className={here ? 'btn border-2 border-ink bg-surface px-md font-semibold text-ink' : 'btn-secondary px-md'}
    >
      {children}
    </Link>
  )
}

export default function UserManagement() {
  const [params] = useSearchParams()
  const view = readView(params)

  // The address is where the screen opens, and the router has already put
  // focus on the page. Only a change of view moves it, to the new heading.
  const heading = useRef<HTMLHeadingElement>(null)
  const viewBefore = useRef(view)
  useEffect(() => {
    if (viewBefore.current === view) return
    viewBefore.current = view
    heading.current?.focus()
  }, [view])

  return (
    <>
      <PageHeader
        screenId="SC-23"
        title="Users, roles and account holds"
        subtitle="Who works here, what they may do, which branch they work at, and which customers may not book right now. Nobody's password is ever shown here."
      />
      <nav aria-label="Parts of the screen" className="mb-lg">
        <ul className="flex flex-wrap gap-sm">
          <li>
            <ViewLink view="staff" current={view}>
              <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
              Staff accounts
            </ViewLink>
          </li>
          <li>
            <ViewLink view="customers" current={view}>
              <Users className="h-4 w-4 shrink-0" aria-hidden="true" />
              Customer holds
            </ViewLink>
          </li>
        </ul>
      </nav>
      <h2 id={VIEW_HEADING_ID} ref={heading} tabIndex={-1} className="mb-md text-lg font-semibold text-ink">
        {VIEW_HEADING[view]}
      </h2>
      {/* The key starts each view afresh, so nothing typed into one is left in the other. */}
      <div key={view}>{view === 'staff' ? <StaffAccounts /> : <CustomerHolds />}</div>
    </>
  )
}
