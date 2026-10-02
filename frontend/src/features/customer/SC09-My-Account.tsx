/**
 * SC-09 My Account and Hire History.
 *
 * The signed in customer's own profile, read from `GET /api/me/profile` and
 * corrected through `PATCH /api/me/profile`. The screen has the shared
 * loading and failed states, and one more for an account that has no customer
 * profile, which is what the API answers a member of staff with.
 *
 * An account whose email address is not confirmed is told so at the top, with
 * a way to send the link again. An account the branch has put on hold is told
 * that too.
 *
 * The hire history and the charges are a later change, and the API has no
 * route for them yet. The card says that hires and charges appear once
 * equipment has been collected, and shows no figure and no sample.
 */

import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { accountQueries, rememberProfile } from '../../shared/api/account-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { formatDate } from '../../shared/format'
import { CATALOGUE_PATH } from '../../shared/navigation'
import { Card, EmptyState, Notice, PageHeader } from '../../shared/ui'
import { AccountProfileCard } from './account-profile-card'
import { isNotFound } from './booking-refusal'
import { EmailVerificationNotice } from './email-verification-notice'
import { MY_RESERVATIONS_PATH } from './reservation-links'

const TITLE = 'My account'

export const NO_PROFILE_TITLE = 'This account has no customer profile'

export const NO_HIRES_YET = 'Hires and charges appear here once equipment has been collected.'

export default function MyAccount() {
  const queryClient = useQueryClient()
  const profile = useQuery(accountQueries.profile())
  const phase = queryPhase(profile)

  if (phase === 'failed' && isNotFound(profile.error)) {
    return (
      <>
        <PageHeader screenId="SC-09" title={TITLE} />
        <div className="card">
          <EmptyState
            title={NO_PROFILE_TITLE}
            body="A customer profile holds the contact and billing details for hires. Staff accounts do not have one, so there is nothing to show or change here."
            action={
              <Link to={CATALOGUE_PATH} className="btn-secondary px-md">
                Back to the catalogue
              </Link>
            }
          />
        </div>
      </>
    )
  }

  if (phase === 'failed') {
    return (
      <>
        <PageHeader screenId="SC-09" title={TITLE} />
        <ErrorState
          what="your account"
          error={profile.error}
          onRetry={() => void profile.refetch()}
        />
      </>
    )
  }

  if (!profile.data) {
    return (
      <>
        <PageHeader screenId="SC-09" title={TITLE} />
        <LoadingState label="Loading your account" shape="detail" count={2} />
      </>
    )
  }

  const customer = profile.data

  return (
    <>
      <PageHeader
        screenId="SC-09"
        title={TITLE}
        subtitle={`${customer.fullName}, with Toolshed Hire since ${formatDate(customer.memberSince)}.`}
        actions={
          <Link to={MY_RESERVATIONS_PATH} className="btn-secondary px-md">
            See my hires
          </Link>
        }
      />

      <div className="flex flex-col gap-lg" aria-busy={profile.isFetching}>
        {!customer.emailVerified && <EmailVerificationNotice email={customer.email} />}

        {customer.accountStatus !== 'ACTIVE' && (
          <Notice tone="error" title="This account cannot book at the moment">
            <p>
              New bookings are blocked until a branch lifts this. Speak to any Toolshed Hire
              counter to sort it out.
            </p>
          </Notice>
        )}

        {/* One column on a phone. Each cell may shrink below what it holds, so
            a long name or address wraps and the page never scrolls sideways. */}
        <div className="grid grid-cols-1 gap-lg lg:grid-cols-3">
          <div className="min-w-0 lg:col-span-2">
            <AccountProfileCard
              profile={customer}
              onSaved={(updated) => rememberProfile(queryClient, updated)}
            />
          </div>

          <div className="min-w-0">
            <Card title="Hire history and charges">
              <p className="text-sm text-slate-soft">{NO_HIRES_YET}</p>
              <p className="mt-sm text-sm text-slate-soft">
                Until then, your bookings are under My Hires, with their dates, the branch and
                what each will cost.
              </p>
            </Card>
          </div>
        </div>
      </div>
    </>
  )
}
