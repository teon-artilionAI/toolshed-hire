/**
 * What a signed in person sees in place of a screen their role does not reach.
 *
 * The guard in App.tsx renders this and never the screen. It says plainly that
 * the screen is not theirs, says who they are signed in as so a person on a
 * shared machine can see why, and offers the home of their own role. It is
 * never a blank page.
 */

import { Link } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import type { ScreenDef } from './navigation'
import { ROLE_HOME, ROLE_LABEL } from './navigation'
import { PageHeader } from './ui'
import { useSession } from './use-session'

export const NO_ACCESS_HEADING = 'You do not have access to this screen'

/** @param screen The screen that was asked for and refused. */
export function NoAccess({ screen }: { screen: ScreenDef }) {
  const { user } = useSession()
  // The guard only refuses a signed in person. A signed out one is sent to
  // sign in, so there is always an account here.
  if (!user) return null
  const account = ROLE_LABEL[user.role].toLowerCase()

  return (
    <>
      <PageHeader title={NO_ACCESS_HEADING} />
      <div className="card p-lg" role="alert">
        <div className="flex items-start gap-sm">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-status-overdue" aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-base font-semibold text-ink">
              {screen.name} is for {ROLE_LABEL[screen.role].toLowerCase()} accounts
            </p>
            <p className="mt-xs text-sm text-slate-soft">
              You are signed in as {user.fullName}, with the role {account}. Nothing has gone wrong
              and nothing has been changed.
            </p>
            <Link to={ROLE_HOME[user.role]} className="btn-primary mt-md px-md">
              Go to my home screen
            </Link>
          </div>
        </div>
      </div>
    </>
  )
}
