/**
 * The staff accounts view of SC-23.
 *
 * The owner finds an account by name or address, by role and by whether it
 * can sign in, opens it to change the name, the phone, the role or the branch,
 * deactivates or reactivates it, and opens new accounts. Every write asks
 * first and says what it did in a notice that takes focus, and the list is
 * read again with the change in it.
 *
 * The filters and the page live in the address, read and written by
 * users-address.ts. The account open and the form are not, because the
 * contract has no route that reads one account, so an address could name an
 * account the screen has no way to show. The open account is the one the list
 * or the last write sent, whichever the screen heard from last.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { UserPlus } from 'lucide-react'
import { adminQueries } from '../../shared/api/admin-queries'
import type { AdminUser, StaffAccountCreated } from '../../shared/api/contract'
import { Notice } from '../../shared/ui'
import { useSession } from '../../shared/use-session'
import { StaffAccount } from './SC23-Staff-Account'
import type { AccessMove } from './SC23-Staff-Access'
import { StaffCreate } from './SC23-Staff-Create'
import StaffList from './SC23-Staff-List'
import { openAccountButtonId } from './staff-form'
import { readStaffFilters, staffQueryFor, writeStaffFilters } from './users-address'
import type { StaffFilters } from './users-address'
import { useBranchList } from './use-branch-list'

const NEW_ACCOUNT_SECTION_ID = 'new-staff-account'

/** What the view says once a write has worked. */
interface Outcome {
  tone: 'success' | 'warn'
  title: string
  lines: string[]
}

/** The account open above the list, as last heard of, and when. */
interface OpenAccount {
  user: AdminUser
  heardAt: number
}

/** What the outcome says once the account is open. The link is promised only
 *  when the server says it could be delivered. */
function createdOutcome({ user, emailDeliverable }: StaffAccountCreated): Outcome {
  if (emailDeliverable) {
    return {
      tone: 'success',
      title: `${user.fullName} has a staff account`,
      lines: [`${user.fullName} sets their own password from a link sent to ${user.email}. Nobody else sees or chooses it.`],
    }
  }
  return {
    tone: 'warn',
    title: `${user.fullName} has a staff account, but the link could not be sent`,
    lines: [
      `This demonstration delivers email to one address only, and ${user.email} is not it, so the link to choose a password will not arrive.`,
      `The account is saved. ${user.fullName} cannot sign in until a link reaches them, and nobody else sees or chooses the password.`,
    ],
  }
}

function accessOutcome(user: AdminUser, move: AccessMove): Outcome {
  if (move === 'deactivate') {
    return {
      tone: 'success',
      title: `${user.fullName} can no longer sign in`,
      lines: ['They were signed out everywhere at once. Reactivate the account to let them back in.'],
    }
  }
  return { tone: 'success', title: `${user.fullName} can sign in again`, lines: ['The audit trail keeps the change.'] }
}

export default function StaffAccounts() {
  const [params, setParams] = useSearchParams()
  const filters = readStaffFilters(params)
  const { user: signedIn } = useSession()
  const branches = useBranchList()
  const list = useQuery(adminQueries.staff(staffQueryFor(filters)))
  const [adding, setAdding] = useState(false)
  const [open, setOpen] = useState<OpenAccount | null>(null)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const outcomeRef = useRef<HTMLDivElement>(null)
  const addButton = useRef<HTMLButtonElement>(null)
  // The account that was closed, so focus can go back to its button in the list.
  const closedAccount = useRef<string | null>(null)

  const show = useCallback(
    (changes: Partial<StaffFilters>) =>
      setParams((current) => writeStaffFilters({ ...readStaffFilters(current), ...changes }), { replace: true }),
    [setParams],
  )

  useEffect(() => {
    if (outcome !== null) outcomeRef.current?.focus()
  }, [outcome])

  useEffect(() => {
    if (open !== null || closedAccount.current === null) return
    const closed = closedAccount.current
    closedAccount.current = null
    document.getElementById(openAccountButtonId(closed))?.focus()
  }, [open])

  // The list read after a write is newer than the write's answer, and the
  // answer is newer than a list read before it.
  const listed = open === null ? undefined : list.data?.items.find((user) => user.id === open.user.id)
  const shown = open === null ? null : listed !== undefined && list.dataUpdatedAt > open.heardAt ? listed : open.user

  function hear(user: AdminUser) {
    setOpen({ user, heardAt: Date.now() })
  }

  function startAdding() {
    setOutcome(null)
    setOpen(null)
    setAdding(true)
  }

  function stopAdding() {
    setAdding(false)
    addButton.current?.focus()
  }

  return (
    <>
      {outcome !== null && (
        <div ref={outcomeRef} tabIndex={-1} className="mb-lg">
          <Notice tone={outcome.tone} title={outcome.title}>
            {outcome.lines.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </Notice>
        </div>
      )}

      <div className="mb-lg">
        <button
          ref={addButton}
          type="button"
          className="btn-primary px-md"
          onClick={startAdding}
          aria-expanded={adding}
          aria-controls={adding ? NEW_ACCOUNT_SECTION_ID : undefined}
        >
          <UserPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
          Add a staff account
        </button>
      </div>

      {adding && (
        <div id={NEW_ACCOUNT_SECTION_ID}>
          <StaffCreate
            onCreated={(created) => {
              setAdding(false)
              setOutcome(createdOutcome(created))
            }}
            onClose={stopAdding}
          />
        </div>
      )}

      {shown !== null && (
        <StaffAccount
          key={shown.id}
          user={shown}
          isYou={shown.id === signedIn?.id}
          branchName={branches.nameOf}
          onSaved={(saved) => {
            hear(saved)
            setOutcome({ tone: 'success', title: `The account of ${saved.fullName} is saved`, lines: ['The audit trail keeps the change.'] })
          }}
          onAccess={(changed, move) => {
            hear(changed)
            setOutcome(accessOutcome(changed, move))
          }}
          onClose={() => {
            closedAccount.current = shown.id
            setOutcome(null)
            setOpen(null)
          }}
        />
      )}

      <StaffList
        filters={filters}
        signedInId={signedIn?.id ?? null}
        branchName={branches.nameOf}
        onShow={show}
        onOpen={(user) => {
          setOutcome(null)
          setAdding(false)
          hear(user)
        }}
        onAdd={startAdding}
      />
    </>
  )
}
