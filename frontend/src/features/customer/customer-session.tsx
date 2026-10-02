/**
 * The sample profile behind the three customer screens that are not connected
 * to the API yet, My Hires, a booking, and My Account.
 *
 * The session says who is signed in, and that is real. The bookings, charges
 * and identification detail these screens show are still sample data, kept
 * against sample customers. This joins the two by email address, so the seeded
 * customer account sees the sample bookings made in its name.
 *
 * An account with no sample profile is shown nothing, and is told why. I never
 * fall back to somebody else's sample bookings, because that would put another
 * person's name and charges in front of a signed in customer as their own.
 *
 * The guard in App.tsx has already dealt with a signed out person and with a
 * staff account before any of these screens render. All of this goes when the
 * screens read the signed in customer's own bookings from the API.
 */

import { Link } from 'react-router-dom'
import { customers } from '../../shared/fixtures'
import type { CustomerProfile } from '../../shared/types'
import { EmptyState } from '../../shared/ui'
import { useSession } from '../../shared/use-session'

/** The sample profile for the signed in customer, or null when the account
 *  has none or the person is not a customer. */
export function useCustomerProfile(): CustomerProfile | null {
  const { user } = useSession()
  if (!user || user.role !== 'customer') return null
  const email = user.email.toLowerCase()
  return customers.find((customer) => customer.email.toLowerCase() === email) ?? null
}

/**
 * Shown in place of a customer screen when the signed in account has no
 * sample profile to show.
 *
 * @param what what the person came here to see, folded into the heading,
 *             for example "your hires".
 */
export function NoSampleProfile({ what }: { what: string }) {
  const { user } = useSession()
  return (
    <div className="card">
      <EmptyState
        title={`We cannot show ${what} yet`}
        body={`This screen still shows sample data, and there is none for ${
          user?.email ?? 'this account'
        }. It will show the bookings on your own account once it is connected.`}
        action={
          <Link to="/" className="btn-secondary px-md">
            Back to the catalogue
          </Link>
        }
      />
    </div>
  )
}
