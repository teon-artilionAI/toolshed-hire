/**
 * The customer's own details on SC-09, and the way in to correcting them.
 *
 * Everything shown is the profile the API sent. A customer may correct their
 * name, their contact and billing details and their company details, through
 * the form in account-profile-form.tsx.
 *
 * The rest is read only, and the card says who changes it. The identity
 * document is what the counter checks a person against before releasing
 * equipment, so changing it is a branch job with the document in hand. The
 * account standing, the trade discount and the customer type are decisions
 * the branch makes. The email address is how the person signs in.
 *
 * Only the last four characters of the identity document are ever shown,
 * because they are all the system holds.
 */

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pencil } from 'lucide-react'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import type { MyProfile } from '../../shared/api/contract'
import { formatDate, percent } from '../../shared/format'
import { Card, Notice } from '../../shared/ui'
import { AccountProfileForm } from './account-profile-form'
import { ACCOUNT_STATUS_LABEL, CUSTOMER_TYPE_LABEL, ID_DOC_LABEL } from './customer-labels'

/** What the card says after the form closes. */
type Outcome = 'saved' | 'unchanged' | null

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-md gap-y-xs border-b border-line py-sm last:border-0">
      <dt className="text-sm text-slate-soft">{term}</dt>
      <dd className="min-w-0 break-words text-sm font-medium text-ink">{children}</dd>
    </div>
  )
}

/** The name of the branch a code stands for, or the code until the names arrive. */
function useBranchName(code: string): string {
  const branches = useQuery(catalogueQueries.branches())
  const branch = branches.data?.items.find((candidate) => candidate.code === code)
  return branch ? `${branch.name}, ${branch.suburb}` : `Branch ${code}`
}

export function AccountProfileCard({
  profile,
  onSaved,
}: {
  profile: MyProfile
  /** Called with the profile the server answered a save with. */
  onSaved: (updated: MyProfile) => void
}) {
  const [editing, setEditing] = useState(false)
  const [outcome, setOutcome] = useState<Outcome>(null)
  const branchName = useBranchName(profile.homeBranchCode)
  const result = useRef<HTMLDivElement>(null)
  const editButton = useRef<HTMLButtonElement>(null)
  const wasEditing = useRef(false)

  // When the form closes, its buttons have gone. Focus moves to what the card
  // says about the save, or back to the button that opened the form.
  useEffect(() => {
    if (editing) {
      wasEditing.current = true
      return
    }
    if (!wasEditing.current) return
    wasEditing.current = false
    if (outcome === null) editButton.current?.focus()
    else result.current?.focus()
  }, [editing, outcome])

  function close(next: Outcome) {
    setEditing(false)
    setOutcome(next)
  }

  return (
    <Card
      title="Your details"
      action={
        !editing && (
          <button
            ref={editButton}
            type="button"
            className="btn-ghost px-sm"
            onClick={() => {
              setOutcome(null)
              setEditing(true)
            }}
          >
            <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
            Edit my details
          </button>
        )
      }
    >
      {editing ? (
        <AccountProfileForm
          profile={profile}
          onSaved={(updated) => {
            onSaved(updated)
            close('saved')
          }}
          onUnchanged={() => close('unchanged')}
          onDiscard={() => close(null)}
        />
      ) : (
        <>
          <div ref={result} tabIndex={-1}>
            {outcome === 'saved' && (
              <div className="mb-md">
                <Notice tone="success" title="Your details have been updated">
                  <p>New bookings and reminders will use these from now on.</p>
                </Notice>
              </div>
            )}
            {outcome === 'unchanged' && (
              <div className="mb-md">
                <Notice tone="info" title="Nothing was changed">
                  <p>Your details are as they were, so nothing was sent.</p>
                </Notice>
              </div>
            )}
          </div>

          <dl>
            <Row term="Name">{profile.fullName}</Row>
            <Row term="Email address">
              <span className="break-all">{profile.email}</span>
            </Row>
            <Row term="Mobile number">
              <span className="tabular">{profile.phone}</span>
            </Row>
            {profile.companyName !== null && <Row term="Company">{profile.companyName}</Row>}
            {profile.vatNumber !== null && (
              <Row term="VAT number">
                <span className="tabular">{profile.vatNumber}</span>
              </Row>
            )}
            <Row term="Billing address">
              {profile.billingAddressLine1}, {profile.billingSuburb}, {profile.billingCity},{' '}
              {profile.billingPostalCode}
            </Row>
            <Row term={ID_DOC_LABEL[profile.idDocumentType]}>
              Ending <span className="font-mono">{profile.idDocumentLast4}</span>
            </Row>
            <Row term="Usual collection branch">{branchName}</Row>
            <Row term="With us since">{formatDate(profile.memberSince)}</Row>
          </dl>

          <h3 className="mt-lg text-sm font-semibold text-ink">Set by the branch</h3>
          <dl className="mt-xs">
            <Row term="Account standing">{ACCOUNT_STATUS_LABEL[profile.accountStatus]}</Row>
            <Row term="Customer type">{CUSTOMER_TYPE_LABEL[profile.customerType]}</Row>
            <Row term="Trade discount">{percent(profile.tradeDiscountPercent)}</Row>
            <Row term="Bookings not collected">{profile.noShowCount}</Row>
          </dl>
          <p className="mt-md text-sm text-slate-soft">
            The branch changes your account standing, your discount and your customer type, so
            they cannot be edited here. Ask at any counter if one of them looks wrong.
          </p>
          <p className="mt-sm text-sm text-slate-soft">
            Your identity document can only be changed at a branch, with the document in hand,
            because the counter checks it before releasing equipment. Your email address is how
            you sign in, so it stays as it is.
          </p>
        </>
      )}
    </Card>
  )
}
