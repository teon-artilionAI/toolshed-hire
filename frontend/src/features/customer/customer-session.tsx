/**
 * Who the signed in customer is, for the three screens that only make sense
 * when someone is signed in.
 *
 * The prototype has no authentication, but "my reservations" and "my
 * account" are meaningless without an answer to "whose". The session holds
 * the account; the customer profile holds the billing and identification
 * detail. This joins the two and gives the screens one honest signed out
 * state to render instead of three different ones.
 */

import { Link } from 'react-router-dom'
import { customers } from '../../shared/fixtures'
import { useSession } from '../../shared/session'
import type { CustomerProfile } from '../../shared/types'
import { EmptyState } from '../../shared/ui'

/** The signed in customer's profile, or null when nobody is signed in or
 *  the signed in account is a staff account. */
export function useCustomerProfile(): CustomerProfile | null {
  const { signedIn, user } = useSession()
  if (!signedIn || !user || user.role !== 'customer') return null
  return (
    customers.find((customer) => customer.userId === user.id) ??
    customers.find((customer) => customer.email === user.email) ??
    null
  )
}

/**
 * Shown in place of a customer screen when nobody is signed in.
 *
 * @param what what the person came here to see, folded into the heading,
 *             for example "your hires".
 */
export function SignInRequired({ what }: { what: string }) {
  const { signedIn, user } = useSession()

  if (signedIn && user && user.role !== 'customer') {
    return (
      <div className="card">
        <EmptyState
          title={`${what} belongs to a customer account`}
          body={`You are signed in as ${user.name}, which is a staff account. Switch to the customer role to see this screen.`}
          action={
            <Link to="/" className="btn-secondary px-md">
              Back to the catalogue
            </Link>
          }
        />
      </div>
    )
  }

  return (
    <div className="card">
      <EmptyState
        title={`Sign in to see ${what}`}
        body="Your bookings, charges and deposits are kept against your account, so we need to know who you are before we can show them."
        action={
          <div className="flex flex-wrap justify-center gap-sm">
            <Link to="/signin" className="btn-primary px-md">
              Sign in
            </Link>
            <Link to="/register" className="btn-secondary px-md">
              Create an account
            </Link>
          </div>
        }
      />
    </div>
  )
}
