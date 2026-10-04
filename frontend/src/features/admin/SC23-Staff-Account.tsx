/**
 * One staff account on SC-23, in a section of its own above the list.
 *
 * The contract has no route that reads one account, so the section shows the
 * account as the list or the last write sent it, and the list is read again
 * after every write. It holds every field of the account, then what can be
 * done with it, which is changing the name, the phone, the role or the branch,
 * and deactivating or reactivating it. Only one of those is open at a time,
 * and putting one away gives focus back to the button that opened it.
 *
 * The section's heading takes focus when it opens, so a keyboard carries on
 * from the top of the account.
 */

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Pencil, Power, PowerOff, X } from 'lucide-react'
import type { AdminUser } from '../../shared/api/contract'
import { StatusPill } from '../../shared/ui'
import { branchDateTime } from '../../shared/today'
import { AccessQuestion } from './SC23-Staff-Access'
import type { AccessMove } from './SC23-Staff-Access'
import { StaffEdit } from './SC23-Staff-Edit'
import { STAFF_ROLE_LABEL, branchWords, lastSignInWords, lockWords, signInPill, verifiedWords } from './staff-words'

const HEADING_ID = 'staff-account-heading'

type Opened = 'nothing' | 'edit' | AccessMove

/** What the section tells the view once a write has worked. */
export interface AccountHandlers {
  onSaved: (user: AdminUser) => void
  onAccess: (user: AdminUser, move: AccessMove) => void
  onClose: () => void
}

function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-soft">{term}</dt>
      <dd className="mt-xs break-words text-sm text-ink">{children}</dd>
    </div>
  )
}

function Facts({ user, branchName }: { user: AdminUser; branchName: (code: string) => string }) {
  const pill = signInPill(user)
  return (
    <dl className="grid gap-md sm:grid-cols-2 lg:grid-cols-4">
      <Fact term="Email">
        <span className="break-all">{user.email}</span>
      </Fact>
      <Fact term="Phone">{user.phone ?? 'None given'}</Fact>
      <Fact term="Role">{STAFF_ROLE_LABEL[user.role]}</Fact>
      <Fact term="Branch">{branchWords(user.branchCode, branchName)}</Fact>
      <Fact term="Signing in">
        <StatusPill status={pill.status} label={pill.label} />
      </Fact>
      <Fact term="Email confirmed">{verifiedWords(user)}</Fact>
      <Fact term="Lock">{lockWords(user)}</Fact>
      <Fact term="Last signed in">{lastSignInWords(user)}</Fact>
      <Fact term="Account opened">{branchDateTime(user.createdAt)}</Fact>
    </dl>
  )
}

export function StaffAccount({
  user,
  isYou,
  branchName,
  onSaved,
  onAccess,
  onClose,
}: AccountHandlers & { user: AdminUser; isYou: boolean; branchName: (code: string) => string }) {
  const [opened, setOpened] = useState<Opened>('nothing')
  const headingRef = useRef<HTMLHeadingElement>(null)
  const buttons = useRef(new Map<Opened, HTMLButtonElement>())
  // What was put away unanswered, so focus can go back to its button once that
  // button is on the page again.
  const putAway = useRef<Opened | null>(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  useEffect(() => {
    if (opened !== 'nothing' || putAway.current === null) return
    buttons.current.get(putAway.current)?.focus()
    putAway.current = null
  }, [opened])

  function keep(which: Opened) {
    return (button: HTMLButtonElement | null) => {
      if (button === null) buttons.current.delete(which)
      else buttons.current.set(which, button)
    }
  }

  function putBack() {
    putAway.current = opened
    setOpened('nothing')
  }

  const access: AccessMove = user.isActive ? 'deactivate' : 'reactivate'

  return (
    <section aria-labelledby={HEADING_ID} className="card mb-lg min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-md border-b border-line px-lg py-md">
        <h3 id={HEADING_ID} ref={headingRef} tabIndex={-1} className="min-w-0 break-words text-lg font-semibold text-ink">
          Account of {user.fullName}
          {isYou && <span className="ml-sm text-sm font-normal text-slate-soft">(you)</span>}
        </h3>
        <button type="button" className="btn-secondary px-md" onClick={onClose}>
          <X className="h-4 w-4 shrink-0" aria-hidden="true" />
          Close the account
        </button>
      </div>
      <div className="flex flex-col gap-lg p-lg">
        <Facts user={user} branchName={branchName} />
        {opened === 'edit' ? (
          <StaffEdit
            user={user}
            onSaved={(saved) => {
              setOpened('nothing')
              onSaved(saved)
            }}
            onClose={putBack}
          />
        ) : opened === 'nothing' ? (
          <div className="flex flex-wrap gap-sm">
            <button ref={keep('edit')} type="button" className="btn-secondary px-md" onClick={() => setOpened('edit')}>
              <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
              Change the name, phone, role or branch
            </button>
            <button
              ref={keep(access)}
              type="button"
              className={access === 'deactivate' ? 'btn-danger px-md' : 'btn-primary px-md'}
              onClick={() => setOpened(access)}
            >
              {access === 'deactivate' ? (
                <PowerOff className="h-4 w-4 shrink-0" aria-hidden="true" />
              ) : (
                <Power className="h-4 w-4 shrink-0" aria-hidden="true" />
              )}
              {access === 'deactivate' ? 'Deactivate the account' : 'Reactivate the account'}
            </button>
          </div>
        ) : (
          <AccessQuestion
            user={user}
            move={opened}
            onDone={(changed) => {
              setOpened('nothing')
              onAccess(changed, opened)
            }}
            onCancel={putBack}
          />
        )}
      </div>
    </section>
  )
}
