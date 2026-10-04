/**
 * One page of the staff accounts on SC-23, as a table.
 *
 * Each account shows the name and the email address, the role in words, the
 * branch, whether the account can sign in beside its colour, whether the
 * address is confirmed, whether a lock after failed sign ins holds, and when
 * the person last signed in. Every value is the server's, in the order the
 * server sent the accounts. The signed in owner's own row says so.
 *
 * Eight columns do not fit across a phone, so below the `lg` width each
 * account is drawn as a block with every value on a line of its own and the
 * name of its column beside it. It is the same table either way, and each part
 * states its role, because changing how a table is displayed can make a
 * browser stop reporting it as one.
 */

import type { ReactNode } from 'react'
import { FolderOpen } from 'lucide-react'
import type { AdminUser } from '../../shared/api/contract'
import { StatusPill } from '../../shared/ui'
import { openAccountButtonId } from './staff-form'
import { STAFF_ROLE_LABEL, branchWords, lastSignInWords, lockWords, signInPill, verifiedWords } from './staff-words'

const COLUMNS = ['Person', 'Role', 'Branch', 'Signing in', 'Email', 'Lock', 'Last signed in', 'Actions'] as const

/** What every cell shares. A table cell from `lg` up, and a line of a block below it. */
const CELL_BASE = 'td px-0 py-xs text-left lg:table-cell lg:px-md lg:py-sm'

/** A cell that shows the name of its column beside its value below `lg`. */
const LABELLED_CELL = `${CELL_BASE} flex flex-wrap items-baseline justify-between gap-x-md`

function Labelled({ column, children }: { column: string; children: ReactNode }) {
  return (
    <td role="cell" className={LABELLED_CELL}>
      <span className="shrink-0 text-sm text-slate-soft lg:hidden">{column}</span>
      <span className="ml-auto min-w-0 text-right text-ink lg:ml-0 lg:text-left">{children}</span>
    </td>
  )
}

function AccountRow({
  user,
  isYou,
  branchName,
  onOpen,
}: {
  user: AdminUser
  isYou: boolean
  branchName: (code: string) => string
  onOpen: () => void
}) {
  const pill = signInPill(user)
  return (
    <tr role="row" className="block px-md py-sm lg:table-row">
      <th role="rowheader" scope="row" className={`${CELL_BASE} block font-medium text-ink`}>
        <span className="block break-words">
          {user.fullName}
          {isYou && <span className="ml-sm text-xs font-normal text-slate-soft">(you)</span>}
        </span>
        <span className="mt-xs block break-all text-xs font-normal text-slate-soft">{user.email}</span>
      </th>
      <Labelled column="Role">{STAFF_ROLE_LABEL[user.role]}</Labelled>
      <Labelled column="Branch">
        <span className="break-words">{branchWords(user.branchCode, branchName)}</span>
      </Labelled>
      <Labelled column="Signing in">
        <StatusPill status={pill.status} label={pill.label} />
      </Labelled>
      <Labelled column="Email">{verifiedWords(user)}</Labelled>
      <Labelled column="Lock">{lockWords(user)}</Labelled>
      <Labelled column="Last signed in">{lastSignInWords(user)}</Labelled>
      <td role="cell" className={`${CELL_BASE} block pt-sm`}>
        <button id={openAccountButtonId(user.id)} type="button" className="btn-secondary px-md" onClick={onOpen}>
          <FolderOpen className="h-4 w-4 shrink-0" aria-hidden="true" />
          Open <span className="sr-only">the account of {user.fullName}</span>
        </button>
      </td>
    </tr>
  )
}

export default function StaffTable({
  accounts,
  signedInId,
  branchName,
  onOpen,
}: {
  accounts: readonly AdminUser[]
  /** The key of the signed in owner's own account, to mark their row. */
  signedInId: string | null
  branchName: (code: string) => string
  onOpen: (user: AdminUser) => void
}) {
  return (
    <div className="table-wrap">
      <table role="table" className="block w-full border-collapse lg:table">
        <caption className="sr-only">
          Each staff account with its role, its branch, whether it can sign in, whether its email is confirmed, any
          lock and when the person last signed in.
        </caption>
        <thead role="rowgroup" className="hidden border-b border-line bg-muted lg:table-header-group">
          <tr role="row">
            {COLUMNS.map((heading) => (
              <th key={heading} role="columnheader" scope="col" className="th whitespace-normal">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup" className="block divide-y divide-line lg:table-row-group">
          {accounts.map((user) => (
            <AccountRow
              key={user.id}
              user={user}
              isYou={user.id === signedInId}
              branchName={branchName}
              onOpen={() => onOpen(user)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
