/**
 * SC-23, User and role management.
 *
 * Two jobs on one screen because they are the same job: deciding who may do
 * what. Staff accounts carry a role and a branch and can be switched off,
 * and customer accounts can be put on hold after a no show without losing
 * their history.
 *
 * The interesting part is the rules that refuse. You cannot switch off your
 * own account, and you cannot leave the business with no active admin,
 * because either would lock everybody out of this very screen. Both refusals
 * say what happened and what to do instead.
 */

import { useMemo, useState } from 'react'
import { UserPlus, X } from 'lucide-react'
import { branches, customers, users } from '../../shared/fixtures'
import type {
  BranchCode,
  CustomerProfile,
  Role,
  UserAccount,
} from '../../shared/types'
import { Card, Field, Notice, PageHeader, StatTile } from '../../shared/ui'
import { useSession } from '../../shared/session'
import StaffAccountForm from './StaffAccountForm'
import StaffAccountsTable from './StaffAccountsTable'
import CustomerHolds from './CustomerHolds'
import type { HoldChange } from './CustomerHolds'

const ROLE_TEXT: Record<Role, string> = {
  customer: 'Customer',
  counter: 'Counter staff',
  admin: 'Admin and owner',
}

/** The branch a demoted admin lands at until somebody says otherwise. */
const FALLBACK_BRANCH: BranchCode = 'CBD'

interface Feedback {
  tone: 'success' | 'error'
  title: string
  body: string
}

export default function UserManagement() {
  const { user: signedInUser } = useSession()
  const [accounts, setAccounts] = useState<UserAccount[]>(users)
  const [customerList, setCustomerList] = useState<CustomerProfile[]>(customers)
  const [customerQuery, setCustomerQuery] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [feedback, setFeedback] = useState<Feedback | null>(null)

  const staff = useMemo(
    () => accounts.filter((a) => a.role !== 'customer'),
    [accounts],
  )
  const activeAdmins = staff.filter((a) => a.role === 'admin' && a.active)
  const onHoldCount = customerList.filter((c) => c.onHold).length

  /** The one account that must never be switched off or demoted. */
  function isLastActiveAdmin(account: UserAccount): boolean {
    return (
      account.role === 'admin' &&
      account.active &&
      activeAdmins.length === 1 &&
      activeAdmins[0].id === account.id
    )
  }

  function update(id: string, change: Partial<UserAccount>) {
    setAccounts((current) =>
      current.map((a) => (a.id === id ? { ...a, ...change } : a)),
    )
  }

  function refuse(title: string, body: string) {
    setFeedback({ tone: 'error', title, body })
  }

  function changeRole(account: UserAccount, role: Role) {
    if (role !== 'admin' && isLastActiveAdmin(account)) {
      refuse(
        'That would leave nobody in charge',
        `${account.name} is the only active admin. Make somebody else an admin first, then change this account.`,
      )
      return
    }
    update(account.id, {
      role,
      branchCode:
        role === 'admin' ? undefined : (account.branchCode ?? FALLBACK_BRANCH),
    })
    setFeedback({
      tone: 'success',
      title: 'Role changed',
      body: `${account.name} is now ${ROLE_TEXT[role].toLowerCase()}. The change applies the next time they sign in.`,
    })
  }

  function changeBranch(account: UserAccount, branchCode?: BranchCode) {
    update(account.id, { branchCode })
    const where = branchCode
      ? branches.find((b) => b.code === branchCode)?.name
      : 'all three branches'
    setFeedback({
      tone: 'success',
      title: 'Branch changed',
      body: `${account.name} now works at ${where}.`,
    })
  }

  function toggleActive(account: UserAccount) {
    if (account.active && account.id === signedInUser?.id) {
      refuse(
        'You cannot switch off your own account',
        'Ask another admin to do it, so nobody locks themselves out of this screen by accident.',
      )
      return
    }
    if (account.active && isLastActiveAdmin(account)) {
      refuse(
        'That would leave nobody in charge',
        `${account.name} is the only active admin. Make somebody else an admin first, then switch this account off.`,
      )
      return
    }
    update(account.id, { active: !account.active })
    setFeedback({
      tone: 'success',
      title: account.active ? 'Account switched off' : 'Account switched back on',
      body: account.active
        ? `${account.name} can no longer sign in. Their history and past bookings are untouched.`
        : `${account.name} can sign in again from now.`,
    })
  }

  function createAccount(draft: Omit<UserAccount, 'id'>) {
    const account: UserAccount = { ...draft, id: `us-${accounts.length + 1}` }
    setAccounts((current) => [...current, account])
    setFormOpen(false)
    setFeedback({
      tone: 'success',
      title: 'Staff account created',
      body: `${account.name} can sign in as ${ROLE_TEXT[account.role].toLowerCase()}. Send them the sign-in address and they set their own password.`,
    })
  }

  function changeHold({ customerId, onHold, reason }: HoldChange) {
    const customer = customerList.find((c) => c.id === customerId)
    setCustomerList((current) =>
      current.map((c) => (c.id === customerId ? { ...c, onHold } : c)),
    )
    setFeedback({
      tone: 'success',
      title: onHold ? 'Account placed on hold' : 'Hold lifted',
      body: onHold
        ? `${customer?.name} cannot make a new booking until the hold is lifted. Reason recorded: ${reason}.`
        : `${customer?.name} can book again from now.`,
    })
  }

  return (
    <>
      <PageHeader
        screenId="SC-23"
        title="Users, roles and account holds"
        subtitle="Who works here, what they may do, which branch they stand in, and which customers are not allowed to book right now."
        actions={
          <button
            type="button"
            className={formOpen ? 'btn-secondary px-md' : 'btn-primary px-md'}
            onClick={() => setFormOpen(!formOpen)}
            aria-expanded={formOpen}
            aria-controls="new-staff-account"
          >
            {formOpen ? (
              <X className="h-4 w-4 shrink-0" aria-hidden="true" />
            ) : (
              <UserPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
            )}
            {formOpen ? 'Close the form' : 'Add a staff account'}
          </button>
        }
      />

      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Staff who can sign in"
          value={staff.filter((a) => a.active).length}
          hint={`Out of ${staff.length} accounts on file`}
        />
        <StatTile
          label="Switched off"
          value={staff.filter((a) => !a.active).length}
          tone={staff.some((a) => !a.active) ? 'warn' : 'default'}
          hint="Kept for the audit trail, cannot sign in"
        />
        <StatTile
          label="Admins"
          value={activeAdmins.length}
          hint="At least one must stay active at all times"
        />
        <StatTile
          label="Customers on hold"
          value={onHoldCount}
          tone={onHoldCount > 0 ? 'bad' : 'good'}
          hint="Blocked from making a new booking"
        />
      </div>

      {feedback && (
        <div className="mb-lg">
          <Notice tone={feedback.tone} title={feedback.title}>
            {feedback.body}
          </Notice>
        </div>
      )}

      {formOpen && (
        <div className="mb-lg" id="new-staff-account">
          <Card title="New staff account">
            <StaffAccountForm
              takenEmails={accounts.map((a) => a.email.toLowerCase())}
              onCreate={createAccount}
              onCancel={() => setFormOpen(false)}
            />
          </Card>
        </div>
      )}

      <div className="mb-lg">
        <Card title="Staff accounts">
          <StaffAccountsTable
            staff={staff}
            signedInUserId={signedInUser?.id}
            onChangeRole={changeRole}
            onChangeBranch={changeBranch}
            onToggleActive={toggleActive}
          />
        </Card>
      </div>

      <Card title="Customer accounts and holds">
        <div className="mb-lg max-w-md">
          <Field
            label="Search customers"
            htmlFor="customer-search"
            help="A hold blocks new bookings. It leaves the customer's history and open hires alone."
          >
            <input
              id="customer-search"
              type="search"
              className="field-input"
              placeholder="Riaan, or riaan@"
              value={customerQuery}
              aria-describedby="customer-search-help"
              onChange={(e) => setCustomerQuery(e.target.value)}
            />
          </Field>
        </div>
        <CustomerHolds
          customers={customerList}
          query={customerQuery}
          onChange={changeHold}
        />
      </Card>
    </>
  )
}
